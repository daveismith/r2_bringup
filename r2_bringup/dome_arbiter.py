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
Arbitration between the joystick and Foxglove for the dome's velocity command.

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
* Otherwise the command is zero (``idle``).

Times are seconds from any monotonic clock; the caller passes ``now``.
"""

SOURCE_JOYSTICK = 'joystick'
SOURCE_FOXGLOVE = 'foxglove'
SOURCE_IDLE = 'idle'


class DomeCommandArbiter:
    """Decide which source drives the dome and what velocity to send."""

    def __init__(self, joystick_hold_s=0.5, joystick_timeout_s=0.5, foxglove_timeout_s=0.5,
                 zero_epsilon=1e-6):
        self.joystick_hold_s = float(joystick_hold_s)
        self.joystick_timeout_s = float(joystick_timeout_s)
        self.foxglove_timeout_s = float(foxglove_timeout_s)
        self.zero_epsilon = float(zero_epsilon)
        self._joy_value = 0.0
        self._joy_time = None          # time of the latest joystick message
        self._joy_active_time = None   # time of the latest non-zero joystick command
        self._fox_value = 0.0
        self._fox_time = None

    def joystick(self, value, now):
        """Record a joystick command (rad/s, already scaled) received at ``now``."""
        value = float(value)
        self._joy_value = value
        self._joy_time = now
        if abs(value) > self.zero_epsilon:
            self._joy_active_time = now

    def foxglove(self, value, now):
        """Record a Foxglove command (rad/s, already scaled) received at ``now``."""
        self._fox_value = float(value)
        self._fox_time = now

    def joystick_owns(self, now):
        """Return True while the joystick has authority (see the module docstring)."""
        if self._joy_time is None or now - self._joy_time > self.joystick_timeout_s:
            return False
        if abs(self._joy_value) > self.zero_epsilon:
            return True
        return (self._joy_active_time is not None and
                now - self._joy_active_time <= self.joystick_hold_s)

    def command(self, now):
        """Return ``(velocity_rad_s, source)`` for time ``now``."""
        if self.joystick_owns(now):
            return self._joy_value, SOURCE_JOYSTICK
        if self._fox_time is not None and now - self._fox_time <= self.foxglove_timeout_s:
            return self._fox_value, SOURCE_FOXGLOVE
        return 0.0, SOURCE_IDLE


def twist_field(twist, field):
    """Read ``linear.x``-style ``field`` from a Twist-like object."""
    try:
        part, axis = field.split('.')
        return float(getattr(getattr(twist, part), axis))
    except (ValueError, AttributeError) as exc:
        raise ValueError(
            "twist field must be like 'linear.x' or 'angular.z', got %r" % field) from exc
