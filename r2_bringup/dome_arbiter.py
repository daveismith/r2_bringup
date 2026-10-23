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
Arbitration between the joystick, Foxglove and the personality for the dome's velocity.

Pure Python (no ROS imports) so the rules can be unit tested. The joystick
stream never goes quiet (joy_node autorepeats and teleop_twist_joy publishes a
zero on every joy message), so precedence is decided by *input*, not by who
published last:

* The joystick owns the dome while its latest command is non-zero and for
  ``joystick_hold_s`` after its last non-zero command; during that hold its
  zeros are forwarded, so releasing the trigger stops the dome even while
  Foxglove is pushing. A joystick stream older than ``joystick_timeout_s``
  (joy_node gone) is ignored.
* Otherwise Foxglove's latest command is used while it is younger than
  ``foxglove_timeout_s``. Foxglove's Teleop panel publishes plain Twist with
  no stamp and no guaranteed zero on release, so this timeout is what stops
  the dome when the panel goes away.
* Otherwise the personality's latest command (``/dome/cmd/personality``) while it is
  younger than ``personality_timeout_s``. Only this source is capped: |v| is limited to
  ``personality_max_speed_rad_s`` and the change from the value last *sent* (by any source)
  to ``personality_max_accel_rad_s2`` times the time since the previous decision (at most
  ``max_tick_s``), so a joystick release does not let the personality jump. Only increases
  in magnitude are rate limited: braking (smaller, same sign, or 0) is applied at once and a
  reversal goes to 0 at once, then ramps up. The real dome's motor has a dead band, so a
  non-zero value below ``personality_min_speed_rad_s`` does nothing: when the last value sent
  is below that floor and the wanted magnitude is at or above it, the first step jumps to the
  floor (with the wanted sign) and the ramp starts from there.
  ``Decision.capped`` is true only when the speed cap clipped the value or the acceleration
  limit held it back by more than one tick's allowance (never for the floor jump alone).
* Otherwise the command is zero (``idle``).

NaN and infinite values are treated as 0. Times are seconds from any monotonic clock; the
caller passes ``now`` and calls ``decide`` once per tick.
"""

import math
from typing import NamedTuple

SOURCE_JOYSTICK = 'joystick'
SOURCE_FOXGLOVE = 'foxglove'
SOURCE_IDLE = 'idle'
SOURCE_PERSONALITY = 'personality'


class Decision(NamedTuple):
    """What to send this tick: velocity (rad/s), its source, and whether it was capped."""

    velocity: float
    source: str
    capped: bool = False


def _finite(value):
    """Return ``value`` as a float, or ``None`` when it is NaN or infinite."""
    value = float(value)
    return value if math.isfinite(value) else None


class DomeCommandArbiter:
    """Decide which source drives the dome and what velocity to send."""

    def __init__(self, joystick_hold_s=0.5, joystick_timeout_s=0.5, foxglove_timeout_s=0.5,
                 personality_timeout_s=0.5, personality_max_speed_rad_s=2.0,
                 personality_max_accel_rad_s2=6.0, max_tick_s=0.1, zero_epsilon=1e-6,
                 personality_min_speed_rad_s=0.6):
        self.joystick_hold_s = float(joystick_hold_s)
        self.joystick_timeout_s = float(joystick_timeout_s)
        self.foxglove_timeout_s = float(foxglove_timeout_s)
        self.personality_timeout_s = float(personality_timeout_s)
        self.personality_max_speed_rad_s = float(personality_max_speed_rad_s)
        self.personality_max_accel_rad_s2 = float(personality_max_accel_rad_s2)
        self.personality_min_speed_rad_s = float(personality_min_speed_rad_s)
        self.max_tick_s = float(max_tick_s)
        self.zero_epsilon = float(zero_epsilon)
        self._joy_value = 0.0
        self._joy_time = None          # time of the latest joystick message
        self._joy_active_time = None   # time of the latest non-zero joystick command
        self._fox_value = 0.0
        self._fox_time = None
        self._per_value = 0.0
        self._per_time = None
        self._last_sent = 0.0          # velocity of the previous decision
        self._last_time = None         # time of the previous decision

    def joystick(self, value, now):
        """Record a joystick command (rad/s, already scaled) received at ``now``."""
        value = _finite(value) or 0.0
        self._joy_value = value
        self._joy_time = now
        if abs(value) > self.zero_epsilon:
            self._joy_active_time = now

    def foxglove(self, value, now):
        """Record a Foxglove command (rad/s, already scaled) received at ``now``."""
        self._fox_value = _finite(value) or 0.0
        self._fox_time = now

    def personality(self, value, now):
        """Record a personality command (rad/s) received at ``now``; False if not finite."""
        finite = _finite(value)
        self._per_value = finite or 0.0
        self._per_time = now
        return finite is not None

    def joystick_owns(self, now):
        """Return True while the joystick has authority (see the module docstring)."""
        if self._joy_time is None or now - self._joy_time > self.joystick_timeout_s:
            return False
        if abs(self._joy_value) > self.zero_epsilon:
            return True
        return (self._joy_active_time is not None and
                now - self._joy_active_time <= self.joystick_hold_s)

    def decide(self, now):
        """Return the ``Decision`` for time ``now`` (call once per tick: it keeps state)."""
        dt = self.max_tick_s if self._last_time is None else min(
            max(now - self._last_time, 0.0), self.max_tick_s)
        decision = self._select(now, dt)
        self._last_sent = decision.velocity
        self._last_time = now
        return decision

    def command(self, now):
        """Return ``(velocity_rad_s, source)`` for time ``now`` (see ``decide``)."""
        decision = self.decide(now)
        return decision.velocity, decision.source

    def _select(self, now, dt):
        if self.joystick_owns(now):
            return Decision(self._joy_value, SOURCE_JOYSTICK)
        if self._fox_time is not None and now - self._fox_time <= self.foxglove_timeout_s:
            return Decision(self._fox_value, SOURCE_FOXGLOVE)
        if self._per_time is not None and now - self._per_time <= self.personality_timeout_s:
            return self._capped_personality(dt)
        return Decision(0.0, SOURCE_IDLE)

    def _capped_personality(self, dt):
        limit = self.personality_max_speed_rad_s
        floor = self.personality_min_speed_rad_s
        wanted = max(-limit, min(limit, self._per_value))
        last = self._last_sent
        step = self.personality_max_accel_rad_s2 * dt
        if abs(wanted) <= abs(last) and wanted * last >= 0.0:
            value = wanted   # braking (same sign, smaller, or 0) is never slowed
        elif wanted * last < 0.0:
            value = 0.0      # a reversal passes through 0 at once, then jumps to the floor
        else:
            if abs(last) < floor <= abs(wanted):
                value = math.copysign(floor, wanted)   # the dead band: start at the floor
            elif wanted > 0.0:
                value = min(wanted, last + step)
            else:
                value = max(wanted, last - step)
        speed_clipped = abs(self._per_value) > limit + 1e-9
        held_back = abs(wanted) - abs(value) > step + 1e-9
        return Decision(value, SOURCE_PERSONALITY, speed_clipped or held_back)


def twist_field(twist, field):
    """Read ``linear.x``-style ``field`` from a Twist-like object."""
    try:
        part, axis = field.split('.')
        return float(getattr(getattr(twist, part), axis))
    except (ValueError, AttributeError) as exc:
        raise ValueError(
            "twist field must be like 'linear.x' or 'angular.z', got %r" % field) from exc
