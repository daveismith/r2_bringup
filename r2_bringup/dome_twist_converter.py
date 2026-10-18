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
Dome velocity command node: joystick and Foxglove in, controller command out.

The joystick (TwistStamped) and the Foxglove Teleop panel (plain Twist) are
arbitrated into the ``Float64MultiArray`` the dome velocity controller reads.
The joystick has precedence; see ``r2_bringup.dome_arbiter`` for the rules.
The command is published from a timer, so a source that goes quiet is timed
out and the dome stopped even if no message ever says so; one final zero is
sent when both sources are idle.
"""

import time

from geometry_msgs.msg import Twist
from geometry_msgs.msg import TwistStamped
from r2_bringup.dome_arbiter import DomeCommandArbiter
from r2_bringup.dome_arbiter import SOURCE_IDLE
from r2_bringup.dome_arbiter import twist_field
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64MultiArray


class DomeTwistConverter(Node):
    """Arbitrate joystick and Foxglove commands into the dome controller's command."""

    def __init__(self):
        super().__init__('dome_twist_converter')
        self.declare_parameter('joystick_topic', 'cmd_vel_dome')
        self.declare_parameter('joystick_field', 'linear.x')
        self.declare_parameter('foxglove_topic', 'cmd_vel_dome_foxglove')
        self.declare_parameter('foxglove_field', 'angular.z')
        self.declare_parameter('foxglove_scale', -1.5)
        self.declare_parameter('joystick_hold_s', 0.5)
        self.declare_parameter('joystick_timeout_s', 0.5)
        self.declare_parameter('foxglove_timeout_s', 0.5)
        self.declare_parameter('publish_rate_hz', 20.0)
        self.declare_parameter('output_topic', 'dome_controller/commands')

        p = self.get_parameter
        self._joystick_field = str(p('joystick_field').value)
        self._foxglove_field = str(p('foxglove_field').value)
        self._foxglove_scale = float(p('foxglove_scale').value)
        for name in ('joystick_hold_s', 'joystick_timeout_s', 'foxglove_timeout_s',
                     'publish_rate_hz'):
            if not float(p(name).value) > 0.0:
                raise ValueError('%s must be > 0, got %r' % (name, p(name).value))
        for field in (self._joystick_field, self._foxglove_field):
            twist_field(Twist(), field)   # validates the field name
        self._arbiter = DomeCommandArbiter(
            joystick_hold_s=float(p('joystick_hold_s').value),
            joystick_timeout_s=float(p('joystick_timeout_s').value),
            foxglove_timeout_s=float(p('foxglove_timeout_s').value))
        self._last_source = SOURCE_IDLE

        self._publisher = self.create_publisher(
            Float64MultiArray, str(p('output_topic').value), 10)
        self.create_subscription(TwistStamped, str(p('joystick_topic').value),
                                 self._on_joystick, 10)
        self.create_subscription(Twist, str(p('foxglove_topic').value), self._on_foxglove, 10)
        self.create_timer(1.0 / float(p('publish_rate_hz').value), self._on_timer)
        self.get_logger().info(
            'Dome command arbiter: joystick %s (%s) has precedence, Foxglove %s (%s x %.2f), '
            'hold %.2f s, timeouts %.2f / %.2f s, output %s' % (
                p('joystick_topic').value, self._joystick_field, p('foxglove_topic').value,
                self._foxglove_field, self._foxglove_scale, self._arbiter.joystick_hold_s,
                self._arbiter.joystick_timeout_s, self._arbiter.foxglove_timeout_s,
                p('output_topic').value))

    def _on_joystick(self, msg: TwistStamped):
        self._arbiter.joystick(twist_field(msg.twist, self._joystick_field), time.monotonic())

    def _on_foxglove(self, msg: Twist):
        self._arbiter.foxglove(twist_field(msg, self._foxglove_field) * self._foxglove_scale,
                               time.monotonic())

    def _on_timer(self):
        value, source = self._arbiter.command(time.monotonic())
        if source != self._last_source:
            self.get_logger().info('Dome command source: %s' % source)
            self._last_source = source
        elif source == SOURCE_IDLE:
            return   # the zero was sent when the source went idle
        msg = Float64MultiArray()
        msg.data = [value]
        self._publisher.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = DomeTwistConverter()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
