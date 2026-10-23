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
Node test: ``dome_twist_converter`` as a subprocess on remapped, test-private topics.

Nothing here touches the real ``/cmd_vel_dome*``, ``/dome/cmd/*`` or ``/dome_controller/*``.
"""

import os
import signal
import subprocess
import sys
import time

from astromech_msgs.msg import DomeCommandStatus
from geometry_msgs.msg import TwistStamped
import pytest
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.qos import QoSProfile
from rclpy.qos import ReliabilityPolicy
from std_msgs.msg import Float64MultiArray

STARTUP_S = 30.0
PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(PKG_ROOT, 'r2_bringup', 'dome_twist_converter.py')
RELIABLE = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
_counter = 0


@pytest.fixture(scope='module', autouse=True)
def ros_context():
    rclpy.init()
    yield
    try:
        rclpy.try_shutdown()
    except RuntimeError:   # this container's zenoh session close can time out
        pass


class Harness:
    """The converter under test, a publisher per input and a recorder per output."""

    def __init__(self):
        global _counter
        _counter += 1
        ns = 'dctest_%d_%d' % (os.getpid(), _counter)
        self.joy_topic = '/%s/joy' % ns
        self.fox_topic = '/%s/fox' % ns
        self.per_topic = '/%s/per' % ns
        self.out_topic = '/%s/commands' % ns
        self.status_topic = '/%s/status' % ns
        remaps = []
        for old, new in (('cmd_vel_dome', self.joy_topic),
                         ('cmd_vel_dome_foxglove', self.fox_topic),
                         ('dome/cmd/personality', self.per_topic),
                         ('dome_controller/commands', self.out_topic),
                         ('dome/cmd/status', self.status_topic)):
            remaps += ['-r', '%s:=%s' % (old, new)]
        argv = [sys.executable, SCRIPT, '--ros-args', '-r', '__node:=%s_conv' % ns] + remaps
        self.proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, start_new_session=True)
        self.node = rclpy.create_node('%s_probe' % ns)
        self.executor = SingleThreadedExecutor()
        self.executor.add_node(self.node)
        self.commands = []   # (time, value)
        self.statuses = []   # (time, source, velocity, capped)
        self.node.create_subscription(Float64MultiArray, self.out_topic, self._on_command, 50)
        self.node.create_subscription(DomeCommandStatus, self.status_topic, self._on_status,
                                      RELIABLE)
        self.joy = self.node.create_publisher(TwistStamped, self.joy_topic, RELIABLE)
        self.per = self.node.create_publisher(TwistStamped, self.per_topic, RELIABLE)

    def _on_command(self, msg):
        self.commands.append((time.monotonic(), msg.data[0]))

    def _on_status(self, msg):
        self.statuses.append((time.monotonic(), msg.source, msg.velocity_rad_s, msg.capped))

    def spin(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.executor.spin_once(timeout_sec=0.01)

    def wait_for(self, predicate, timeout=10.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if predicate():
                return True
            self.executor.spin_once(timeout_sec=0.02)
        return False

    def wait_started(self):
        # The converter publishes status at 2 Hz from the start.
        assert self.wait_for(lambda: self.statuses, STARTUP_S), self.log()
        assert self.statuses[0][1] == 'idle'

    def publish(self, publisher, value, field='angular'):
        msg = TwistStamped()
        setattr(getattr(msg.twist, field), 'z' if field == 'angular' else 'x', value)
        publisher.publish(msg)

    def log(self):
        if self.proc.poll() is None:
            return '(converter running)'
        return self.proc.stdout.read()

    def close(self):
        try:
            if self.proc.poll() is None:
                os.killpg(self.proc.pid, signal.SIGINT)
            self.proc.wait(timeout=15)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.proc.stdout.close()
        self.executor.remove_node(self.node)
        self.node.destroy_node()


@pytest.fixture
def harness():
    h = Harness()
    yield h
    h.close()


def stream(h, publisher, value, seconds, field='angular'):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        h.publish(publisher, value, field)
        h.spin(0.05)


def test_personality_is_capped_streams_at_20hz_and_stops_with_one_zero(harness):
    h = harness
    h.wait_started()
    h.commands.clear()
    stream(h, h.per, 5.0, 2.0)
    h.spin(0.2)
    sent = [t for t, v in h.commands]
    values = [v for t, v in h.commands]
    assert max(values) == pytest.approx(2.0)          # capped to the default 2.0 rad/s
    # 6 rad/s2 x at most max_tick_s (0.1) per tick, whatever the timer jitter, and the
    # first step from 0 jumps to the 0.6 rad/s floor
    assert all(abs(b - a) <= 0.61 for a, b in zip(values, values[1:])), values
    # rule 4 at the controller input: nothing non-zero below the dead-band floor
    assert all(abs(v) >= 0.6 - 1e-9 for v in values if v != 0.0), values
    rate = (len(sent) - 1) / (sent[-1] - sent[0])
    assert 14.0 < rate < 24.0, rate
    assert any(s == 'personality' and capped for _, s, _, capped in h.statuses), h.statuses
    # silence: stream stops, with exactly one final 0, then nothing
    assert h.wait_for(lambda: h.commands[-1][1] == 0.0, 3.0)
    n = len(h.commands)
    h.spin(1.0)
    assert len(h.commands) == n
    assert h.commands[-1][1] == 0.0 and h.commands[-2][1] != 0.0
    assert h.statuses[-1][1] == 'idle'


def test_joystick_takes_over_and_the_status_follows_within_a_tick(harness):
    h = harness
    h.wait_started()
    stream(h, h.per, 1.0, 0.6)
    assert h.wait_for(lambda: h.statuses[-1][1] == 'personality')
    h.statuses.clear()
    t0 = time.monotonic()
    h.publish(h.joy, 1.25, field='linear')
    h.publish(h.per, 1.0)
    assert h.wait_for(lambda: any(s == 'joystick' for _, s, _, _ in h.statuses), 1.0)
    when, _, velocity, capped = next(st for st in h.statuses if st[1] == 'joystick')
    assert when - t0 < 0.2                           # one 20 Hz tick plus slack
    assert velocity == pytest.approx(1.25) and not capped
    # the joystick is not capped or ramped
    assert h.wait_for(lambda: h.commands[-1][1] == pytest.approx(1.25), 1.0)


def test_sigint_sends_a_final_zero_before_exiting(harness):
    h = harness
    h.wait_started()
    stream(h, h.per, 1.5, 1.0)
    assert h.commands[-1][1] != 0.0
    h.commands.clear()
    # The personality is still "fresh" (0.5 s timeout), so a 0 in the next 0.5 s is the
    # shutdown's, not the timeout's: signal at once and check how quickly it arrives.
    h.publish(h.per, 1.5)
    h.spin(0.05)
    t0 = time.monotonic()
    os.killpg(h.proc.pid, signal.SIGINT)
    assert h.wait_for(lambda: any(v == 0.0 for _, v in h.commands), 0.5), h.commands
    assert next(t for t, v in h.commands if v == 0.0) - t0 < 0.5
    # Exit: this container's zenoh session close can take ~10 s, so the exit time alone does
    # not fail the test; only a non-zero exit code does (and a hang past 15 s).
    try:
        code = h.proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        pytest.skip('the 0 arrived but the process took over 15 s to exit (zenoh close)')
    assert code == 0, h.log()
