#!/usr/bin/env python3
# Copyright (c) 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Dome velocity command node: joystick, Foxglove and personality in, controller command out.

The joystick (TwistStamped), the Foxglove Teleop panel (plain Twist) and the personality
(TwistStamped, ``angular.z``) are arbitrated into the ``Float64MultiArray`` the dome velocity
controller reads, in that order of precedence; only the personality is speed and
acceleration capped. See ``r2_bringup.dome_arbiter`` for the rules. Who drove the dome is
published as ``astromech_msgs/DomeCommandStatus`` on every source change and at ``status_hz``.
On SIGINT/SIGTERM (or an exception) one final zero is published before the node closes: the
controller holds its last command and the motor driver has no timeout.
The command is published from a timer, so a source that goes quiet is timed
out and the dome stopped even if no message ever says so; one final zero is
sent when all sources are idle (a personality timeout stops the dome at once, unramped).
"""

import signal
import time

from astromech_msgs.msg import DomeCommandStatus
from geometry_msgs.msg import Twist
from geometry_msgs.msg import TwistStamped
from r2_bringup.dome_arbiter import Decision
from r2_bringup.dome_arbiter import DomeCommandArbiter
from r2_bringup.dome_arbiter import SOURCE_IDLE
from r2_bringup.dome_arbiter import twist_field
import rclpy
from rclpy.duration import Duration
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile
from rclpy.qos import ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions
from std_msgs.msg import Float64MultiArray

CLOSE_ACK_S = 0.2   # how long the final 0 gets to leave before the session closes


class DomeTwistConverter(Node):
    """Arbitrate joystick, Foxglove and personality commands into the dome controller's command."""

    def __init__(self):
        super().__init__('dome_twist_converter')
        self.declare_parameter('joystick_topic', 'cmd_vel_dome')
        self.declare_parameter('joystick_field', 'linear.x')
        self.declare_parameter('foxglove_topic', 'cmd_vel_dome_foxglove')
        self.declare_parameter('foxglove_field', 'angular.z')
        self.declare_parameter('foxglove_scale', 1.5)
        self.declare_parameter('joystick_hold_s', 0.5)
        self.declare_parameter('joystick_timeout_s', 0.5)
        self.declare_parameter('foxglove_timeout_s', 0.5)
        self.declare_parameter('personality_topic', 'dome/cmd/personality')
        self.declare_parameter('personality_field', 'angular.z')
        self.declare_parameter('personality_timeout_s', 0.5)
        self.declare_parameter('personality_max_speed_rad_s', 2.0)
        self.declare_parameter('personality_max_accel_rad_s2', 6.0)
        self.declare_parameter('personality_min_speed_rad_s', 0.6)
        self.declare_parameter('publish_rate_hz', 20.0)
        self.declare_parameter('status_hz', 2.0)
        self.declare_parameter('status_topic', 'dome/cmd/status')
        self.declare_parameter('output_topic', 'dome_controller/commands')

        p = self.get_parameter
        self._joystick_field = str(p('joystick_field').value)
        self._foxglove_field = str(p('foxglove_field').value)
        self._foxglove_scale = float(p('foxglove_scale').value)
        self._personality_field = str(p('personality_field').value)
        for name in ('joystick_hold_s', 'joystick_timeout_s', 'foxglove_timeout_s',
                     'personality_timeout_s', 'personality_max_speed_rad_s',
                     'personality_max_accel_rad_s2', 'publish_rate_hz', 'status_hz'):
            if not float(p(name).value) > 0.0:
                raise ValueError('%s must be > 0, got %r' % (name, p(name).value))
        if not float(p('personality_min_speed_rad_s').value) >= 0.0:
            raise ValueError('personality_min_speed_rad_s must be >= 0, got %r' %
                             p('personality_min_speed_rad_s').value)
        for field in (self._joystick_field, self._foxglove_field, self._personality_field):
            twist_field(Twist(), field)   # validates the field name
        self._arbiter = DomeCommandArbiter(
            joystick_hold_s=float(p('joystick_hold_s').value),
            joystick_timeout_s=float(p('joystick_timeout_s').value),
            foxglove_timeout_s=float(p('foxglove_timeout_s').value),
            personality_timeout_s=float(p('personality_timeout_s').value),
            personality_max_speed_rad_s=float(p('personality_max_speed_rad_s').value),
            personality_max_accel_rad_s2=float(p('personality_max_accel_rad_s2').value),
            personality_min_speed_rad_s=float(p('personality_min_speed_rad_s').value),
            max_tick_s=2.0 / float(p('publish_rate_hz').value))   # one missed tick allowed
        self._last_decision = Decision(0.0, SOURCE_IDLE)

        self._publisher = self.create_publisher(
            Float64MultiArray, str(p('output_topic').value), 10)
        self.create_subscription(TwistStamped, str(p('joystick_topic').value),
                                 self._on_joystick, 10)
        self.create_subscription(Twist, str(p('foxglove_topic').value), self._on_foxglove, 10)
        reliable = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE)
        self.create_subscription(TwistStamped, str(p('personality_topic').value),
                                 self._on_personality, reliable)
        self._status_publisher = self.create_publisher(
            DomeCommandStatus, str(p('status_topic').value), reliable)
        self.create_timer(1.0 / float(p('publish_rate_hz').value), self._on_timer)
        self.create_timer(1.0 / float(p('status_hz').value), self._publish_status)
        self.get_logger().info(
            'Dome command arbiter: joystick %s (%s) has precedence, Foxglove %s (%s x %.2f), '
            'hold %.2f s, timeouts %.2f / %.2f s, personality %s (%s, timeout %.2f s, '
            '%.2f <= |v| <= %.2f rad/s, |a| <= %.2f rad/s2), output %s' % (
                p('joystick_topic').value, self._joystick_field, p('foxglove_topic').value,
                self._foxglove_field, self._foxglove_scale, self._arbiter.joystick_hold_s,
                self._arbiter.joystick_timeout_s, self._arbiter.foxglove_timeout_s,
                p('personality_topic').value, self._personality_field,
                self._arbiter.personality_timeout_s, self._arbiter.personality_min_speed_rad_s,
                self._arbiter.personality_max_speed_rad_s,
                self._arbiter.personality_max_accel_rad_s2, p('output_topic').value))

    def _on_joystick(self, msg: TwistStamped):
        self._arbiter.joystick(twist_field(msg.twist, self._joystick_field), time.monotonic())

    def _on_foxglove(self, msg: Twist):
        self._arbiter.foxglove(twist_field(msg, self._foxglove_field) * self._foxglove_scale,
                               time.monotonic())

    def _on_personality(self, msg: TwistStamped):
        # Arrival time, not msg.header.stamp: a stale stamp must not time the input out.
        if not self._arbiter.personality(twist_field(msg.twist, self._personality_field),
                                         time.monotonic()):
            self.get_logger().warning(
                'Ignoring a non-finite personality dome command (treated as 0)',
                throttle_duration_sec=60.0)

    def _on_timer(self):
        decision = self._arbiter.decide(time.monotonic())
        changed = decision.source != self._last_decision.source
        self._last_decision = decision
        if changed:
            self.get_logger().info('Dome command source: %s' % decision.source)
            self._publish_status()
        elif decision.source == SOURCE_IDLE:
            return   # the zero was sent when the source went idle
        msg = Float64MultiArray()
        msg.data = [decision.velocity]
        self._publisher.publish(msg)

    def stop_dome(self):
        """Publish one 0 and give it a moment to leave (the controller holds its last value)."""
        msg = Float64MultiArray()
        msg.data = [0.0]
        try:
            self._publisher.publish(msg)
            if self._publisher.wait_for_all_acked(Duration(seconds=CLOSE_ACK_S)):
                return
        except Exception:   # the context may be gone already, or the RMW has no acks
            pass
        time.sleep(CLOSE_ACK_S)   # no ack: give the 0 a moment to leave anyway

    def _publish_status(self):
        msg = DomeCommandStatus()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.source = self._last_decision.source
        msg.velocity_rad_s = self._last_decision.velocity
        msg.capped = self._last_decision.capped
        self._status_publisher.publish(msg)


def _interrupt(signum, frame):
    """End the spin loop; a second signal must not break the closing."""
    for each in (signal.SIGINT, signal.SIGTERM):
        signal.signal(each, signal.SIG_IGN)
    raise KeyboardInterrupt


def main(args=None):
    # rclpy's own handlers shut the context down first, and then the final 0 could not be
    # published; here a signal only ends the spin loop and the node closes afterwards.
    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, _interrupt)
    node = None
    executor = None
    try:
        node = DomeTwistConverter()
        executor = SingleThreadedExecutor()
        executor.add_node(node)
        while rclpy.ok():
            executor.spin_once(timeout_sec=0.5)   # a timeout, so a signal is noticed when idle
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.stop_dome()
            if executor is not None:
                executor.shutdown(timeout_sec=0)
            node.destroy_node()
        try:
            rclpy.try_shutdown()
        except RuntimeError:   # a session that is slow to close is not a failure
            pass


if __name__ == '__main__':
    main()
