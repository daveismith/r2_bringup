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

"""Unit tests for the dome command arbiter (no ROS graph)."""

import os
import sys
import types

import pytest

PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PKG_ROOT not in sys.path:
    sys.path.insert(0, PKG_ROOT)

from r2_bringup.dome_arbiter import DomeCommandArbiter  # noqa: E402
from r2_bringup.dome_arbiter import SOURCE_FOXGLOVE, SOURCE_IDLE, SOURCE_JOYSTICK  # noqa: E402
from r2_bringup.dome_arbiter import twist_field  # noqa: E402


def arbiter():
    return DomeCommandArbiter(joystick_hold_s=0.5, joystick_timeout_s=0.5, foxglove_timeout_s=0.5)


def test_idle_until_someone_commands():
    a = arbiter()
    assert a.command(0.0) == (0.0, SOURCE_IDLE)


def test_joystick_zero_stream_does_not_block_foxglove():
    # joy_node autorepeats: teleop_twist_joy publishes zeros all the time.
    a = arbiter()
    for k in range(10):
        a.joystick(0.0, k * 0.05)
    a.foxglove(1.2, 0.46)
    assert a.command(0.5) == (1.2, SOURCE_FOXGLOVE)


def test_joystick_wins_while_non_zero_and_holds_after_release():
    a = arbiter()
    a.foxglove(1.2, 0.0)
    a.joystick(-3.0, 0.0)
    assert a.command(0.01) == (-3.0, SOURCE_JOYSTICK)
    # Released: the joystick's zero is forwarded for joystick_hold_s, Foxglove kept out.
    a.joystick(0.0, 0.1)
    a.foxglove(1.2, 0.1)
    assert a.command(0.11) == (0.0, SOURCE_JOYSTICK)
    a.joystick(0.0, 0.45)
    a.foxglove(1.2, 0.45)
    assert a.command(0.49) == (0.0, SOURCE_JOYSTICK)
    # Hold over: Foxglove takes the dome.
    a.joystick(0.0, 0.55)
    a.foxglove(1.2, 0.55)
    assert a.command(0.56) == (1.2, SOURCE_FOXGLOVE)


def test_foxglove_times_out_to_zero():
    # The Teleop panel may stop publishing without a zero (disconnect, tab closed).
    a = arbiter()
    a.foxglove(1.2, 0.0)
    assert a.command(0.5) == (1.2, SOURCE_FOXGLOVE)
    assert a.command(0.51) == (0.0, SOURCE_IDLE)


def test_joystick_stream_dying_mid_press_times_out():
    a = arbiter()
    a.joystick(-3.0, 0.0)
    assert a.command(0.5) == (-3.0, SOURCE_JOYSTICK)
    assert a.command(0.51) == (0.0, SOURCE_IDLE)
    # ... and a fresh Foxglove command is honoured once the joystick is gone.
    a.foxglove(0.8, 0.6)
    assert a.command(0.61) == (0.8, SOURCE_FOXGLOVE)


def test_tiny_joystick_values_count_as_zero():
    a = arbiter()
    a.joystick(1e-9, 0.0)
    a.foxglove(1.0, 0.0)
    assert a.command(0.01) == (1.0, SOURCE_FOXGLOVE)


def test_twist_field_reads_nested_fields_and_rejects_bad_names():
    twist = types.SimpleNamespace(linear=types.SimpleNamespace(x=1.5, y=0.0, z=0.0),
                                  angular=types.SimpleNamespace(x=0.0, y=0.0, z=-0.7))
    assert twist_field(twist, 'linear.x') == 1.5
    assert twist_field(twist, 'angular.z') == -0.7
    with pytest.raises(ValueError):
        twist_field(twist, 'angular')
    with pytest.raises(ValueError):
        twist_field(twist, 'linear.w')


def test_arbiter_imports_without_rclpy():
    import subprocess
    code = ('import sys; import r2_bringup.dome_arbiter; '
            'sys.exit(1 if "rclpy" in sys.modules else 0)')
    env = dict(os.environ, PYTHONPATH=PKG_ROOT)
    assert subprocess.run([sys.executable, '-B', '-c', code], env=env, check=False).returncode == 0
