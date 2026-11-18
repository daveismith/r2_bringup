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

from r2_bringup.dome_arbiter import Decision  # noqa: E402
from r2_bringup.dome_arbiter import DomeCommandArbiter  # noqa: E402
from r2_bringup.dome_arbiter import SOURCE_FOXGLOVE, SOURCE_IDLE, SOURCE_JOYSTICK  # noqa: E402
from r2_bringup.dome_arbiter import SOURCE_PERSONALITY  # noqa: E402
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


# --- the personality source -------------------------------------------------------------

def run(a, t0, t1, value=None, dt=0.05):
    """Tick ``a`` from t0 to t1, feeding the personality ``value`` each tick; return decisions."""
    out = []
    t = t0
    while t <= t1 + 1e-9:
        if value is not None:
            a.personality(value, t)
        out.append(a.decide(t))
        t += dt
    return out


def test_source_strings():
    assert (SOURCE_IDLE, SOURCE_JOYSTICK, SOURCE_FOXGLOVE, SOURCE_PERSONALITY) == (
        'idle', 'joystick', 'foxglove', 'personality')


def test_decide_returns_a_decision_and_command_keeps_the_old_shape():
    a = arbiter()
    assert a.decide(0.0) == Decision(0.0, SOURCE_IDLE, False)
    a.foxglove(1.0, 1.0)
    assert a.command(1.0) == (1.0, SOURCE_FOXGLOVE)


def test_joystick_beats_foxglove_beats_personality():
    a = arbiter()
    a.personality(1.0, 0.0)
    a.foxglove(0.5, 0.0)
    a.joystick(0.25, 0.0)
    assert a.decide(0.01)[:2] == (0.25, SOURCE_JOYSTICK)
    a.foxglove(0.5, 0.4)
    a.personality(1.0, 0.4)
    # the joystick stream timed out (0.5 s), foxglove is fresh
    assert a.decide(0.6)[:2] == (0.5, SOURCE_FOXGLOVE)
    a.personality(1.0, 0.8)
    assert a.decide(0.85).source == SOURCE_FOXGLOVE
    assert a.decide(0.95).source == SOURCE_PERSONALITY


def test_joystick_hold_and_forwarded_zeros_unchanged_with_personality_pushing():
    a = arbiter()
    a.joystick(1.0, 0.0)
    a.joystick(0.0, 0.1)
    for t in (0.1, 0.3, 0.45):
        a.personality(1.5, t)
        assert a.decide(t)[:2] == (0.0, SOURCE_JOYSTICK)
        a.joystick(0.0, t)
    a.personality(1.5, 0.7)
    assert a.decide(0.7).source == SOURCE_PERSONALITY


def test_personality_times_out_to_idle_zero():
    a = arbiter()
    a.personality(1.0, 0.0)
    run(a, 0.0, 0.5, value=None)
    assert a.decide(0.5).source == SOURCE_PERSONALITY
    assert a.decide(0.51) == Decision(0.0, SOURCE_IDLE, False)


def test_personality_speed_cap():
    a = DomeCommandArbiter(personality_max_speed_rad_s=2.0, personality_max_accel_rad_s2=1000.0)
    d = run(a, 0.0, 0.1, value=5.0)[-1]
    assert d == Decision(2.0, SOURCE_PERSONALITY, True)
    d = run(a, 0.15, 0.25, value=-5.0)[-1]   # 0, the floor, then the cap
    assert d == Decision(-2.0, SOURCE_PERSONALITY, True)


def test_personality_below_caps_is_not_flagged():
    a = DomeCommandArbiter(personality_max_accel_rad_s2=1000.0)
    assert run(a, 0.0, 0.1, value=1.0)[-1] == Decision(1.0, SOURCE_PERSONALITY, False)


def test_personality_cold_start_jumps_to_the_floor_then_ramps():
    a = DomeCommandArbiter()   # 2 rad/s, 6 rad/s2, floor 0.6
    a.decide(0.0)
    ds = run(a, 0.05, 0.6, value=2.0, dt=0.05)
    assert ds[0].velocity == pytest.approx(0.6)
    assert ds[0].capped                       # 2.0 asked, 1.4 short of it is > one tick
    assert ds[1].velocity == pytest.approx(0.9)
    assert ds[5].velocity == pytest.approx(2.0) and not ds[5].capped
    assert all(abs(d.velocity) >= 0.6 for d in ds)
    assert all(abs(y.velocity - x.velocity) <= 0.3 + 1e-9 for x, y in zip(ds[1:], ds[2:]))


@pytest.mark.parametrize('sign', [1.0, -1.0])
def test_floor_jump_from_zero_in_both_directions(sign):
    a = DomeCommandArbiter()
    a.decide(0.0)
    a.personality(sign * 0.6, 0.05)
    assert a.decide(0.05) == Decision(sign * 0.6, SOURCE_PERSONALITY, False)
    b = DomeCommandArbiter()
    b.decide(0.0)
    b.personality(sign * 1.0, 0.05)
    d = b.decide(0.05)
    assert d.velocity == pytest.approx(sign * 0.6)    # min(|wanted|, floor)


def test_reversal_goes_to_zero_then_jumps_to_the_floor():
    a = DomeCommandArbiter()
    run(a, 0.0, 1.0, value=1.0)
    a.personality(-1.0, 1.05)
    assert a.decide(1.05).velocity == 0.0
    a.personality(-1.0, 1.1)
    assert a.decide(1.1).velocity == pytest.approx(-0.6)


def test_no_floor_jump_when_wanted_is_below_the_floor():
    a = DomeCommandArbiter()
    a.decide(0.0)
    a.personality(0.3, 0.05)
    assert a.decide(0.05).velocity == pytest.approx(0.3)


def test_floor_can_be_disabled():
    a = DomeCommandArbiter(personality_min_speed_rad_s=0.0, personality_max_accel_rad_s2=4.0)
    a.decide(0.0)
    a.personality(2.0, 0.05)
    assert a.decide(0.05).velocity == pytest.approx(0.2)


def test_capped_is_false_for_a_floor_start_and_a_gentle_ramp():
    a = DomeCommandArbiter()
    a.decide(0.0)
    t = 0.05
    wanted = 0.6
    ds = []
    while wanted < 1.0:
        a.personality(wanted, t)
        ds.append(a.decide(t))
        wanted += 1.5 * 0.05
        t += 0.05
    a.personality(1.0, t)
    ds.append(a.decide(t))
    assert [d.capped for d in ds] == [False] * len(ds)
    assert ds[-1].velocity == pytest.approx(1.0)


def test_capped_is_false_for_a_4_rad_s2_profile_out_of_phase():
    a = DomeCommandArbiter()
    a.decide(0.0)
    t = 0.0
    wanted = 0.6
    for k in range(20):
        t += 0.05
        # the personality's value is one clock behind the converter's tick
        a.personality(wanted, t - 0.049)
        d = a.decide(t)
        assert not d.capped, (k, d)
        wanted = min(2.0, wanted + 4.0 * 0.05)   # a 4 rad/s2 profile sampled every 0.05 s


def test_capped_is_true_when_the_speed_cap_clips():
    a = DomeCommandArbiter(personality_max_speed_rad_s=2.0)
    d = run(a, 0.0, 1.0, value=3.0)[-1]
    assert d == Decision(2.0, SOURCE_PERSONALITY, True)


def test_capped_is_true_when_a_20_rad_s2_jump_is_clipped():
    a = DomeCommandArbiter()
    run(a, 0.0, 0.5, value=0.6)
    a.personality(1.6, 0.55)
    d = a.decide(0.55)
    assert d.velocity == pytest.approx(0.9) and d.capped


def test_acceleration_cap_counts_from_the_last_value_sent_after_a_joystick_release():
    a = DomeCommandArbiter()
    a.decide(0.0)
    # joystick at 1.5 rad/s, then released; hold lasts 0.5 s then personality at 2.0 asks
    t = 0.05
    while t < 0.3:
        a.joystick(1.5, t)
        a.decide(t)
        t += 0.05
    a.joystick(0.0, t)
    last = a.decide(t)
    assert last.velocity == 0.0
    ds = []
    while t < 1.2:
        t += 0.05
        a.joystick(0.0, t)
        a.personality(2.0, t)
        ds.append(a.decide(t))
    first = next(d for d in ds if d.source == SOURCE_PERSONALITY)
    assert first.velocity == pytest.approx(0.6)   # from the 0 the joystick sent: the floor
    assert first.capped


def test_acceleration_cap_from_a_joystick_value_it_took_over_from():
    a = DomeCommandArbiter()
    a.decide(0.0)
    a.joystick(1.5, 0.05)
    assert a.decide(0.05).velocity == 1.5
    # joystick stream dies: its timeout passes, personality asks 0 -> still ramps from last sent
    a.personality(-2.0, 0.6)
    d = a.decide(0.6)   # last sent 1.5: a reversal goes through 0 at once
    assert d.velocity == 0.0 and d.source == SOURCE_PERSONALITY
    a.personality(-2.0, 0.65)
    assert a.decide(0.65).velocity == pytest.approx(-0.6)


def test_braking_is_not_rate_limited_and_a_reversal_passes_through_zero():
    a = DomeCommandArbiter()
    run(a, 0.0, 1.0, value=2.0)
    assert a.decide(1.0).velocity == 2.0
    a.personality(0.0, 1.05)
    assert a.decide(1.05) == Decision(0.0, SOURCE_PERSONALITY, False)   # 0 on the next tick
    run(a, 1.1, 1.6, value=1.0)
    a.personality(0.5, 1.65)
    assert a.decide(1.65).velocity == 0.5                               # smaller, same sign
    b = DomeCommandArbiter()
    run(b, 0.0, 1.0, value=1.0)
    b.personality(-1.0, 1.05)
    assert b.decide(1.05).velocity == 0.0
    b.personality(-1.0, 1.1)
    assert b.decide(1.1).velocity == pytest.approx(-0.6)


def test_decelerating_to_a_stop_by_timeout_is_not_rate_limited():
    a = DomeCommandArbiter()
    run(a, 0.0, 1.0, value=2.0)
    assert a.decide(1.6) == Decision(0.0, SOURCE_IDLE, False)


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), float('-inf')])
def test_non_finite_values_are_zero(bad):
    a = arbiter()
    assert a.personality(bad, 0.0) is False
    assert a.decide(0.0)[:2] == (0.0, SOURCE_PERSONALITY)
    a.foxglove(bad, 1.0)
    assert a.decide(1.0)[:2] == (0.0, SOURCE_FOXGLOVE)
    a.joystick(bad, 2.0)
    assert a.decide(2.0)[:2] == (0.0, SOURCE_IDLE)   # zero never earns the joystick authority
    assert a.personality(1.0, 3.0) is True


def test_other_sources_are_never_capped():
    a = DomeCommandArbiter(personality_max_speed_rad_s=0.5, personality_max_accel_rad_s2=0.1)
    a.joystick(3.0, 0.0)
    assert a.decide(0.0) == Decision(3.0, SOURCE_JOYSTICK, False)
    a.foxglove(-3.0, 1.0)
    assert a.decide(1.0) == Decision(-3.0, SOURCE_FOXGLOVE, False)
