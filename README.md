# r2_bringup

This package includes `r2d2.repos`, a vcstool manifest that can be used to pull all required repositories for the R2 workspace.

## Prerequisites

- ROS 2 installed
- `vcstool` installed (`vcs` command)
- `colcon` installed

On Ubuntu, if needed:

```bash
sudo apt update
sudo apt install python3-vcstool python3-colcon-common-extensions
```

## Robot host setup

Do these once on the robot's Pi (not on a development machine).

- **Disable the automatic apt timers.** Ubuntu's `apt-daily` and
  `apt-daily-upgrade` services run unattended package scans and upgrades at
  random times. On the Pi they load the CPU and disk for 20 to 30 s, and one
  such run coincided with a 1 s gap in the dome controller's position stream
  while the controller manager was running (2026-10-16). Run updates by hand
  instead:

  ```bash
  sudo systemctl disable --now apt-daily.timer apt-daily-upgrade.timer
  sudo systemctl mask apt-daily.service apt-daily-upgrade.service
  systemctl list-timers --all | grep apt-daily   # should list nothing active
  ```

- **Run the control stack at normal priority.** Anything started from a shell
  that has been reniced (some tool environments run at nice 19) inherits that
  priority, including `ros2_control_node`. Check with
  `ps -o pid,ni,comm -C ros2_control_node`; it should show `0`. A second cause
  was found on 2026-10-23: `/etc/security/limits.conf` gave `@realtime` a line
  `priority 99` beside the intended `rtprio 99`. `priority` is a *nice* value, so
  99 clamped to 19 and everything started from a login of that group, the whole
  stack included, ran at nice 19. Delete the two `priority` lines (keep `rtprio`),
  log in again, and for a stack already running use `sudo renice -n 0 -u pi`.

- **Install the device rules and CAN interface files.** The udev rules, the two
  `systemd-networkd` CAN files and the MCP2515 overlay in `config.txt` are listed, with
  their contents and how to check them, in
  [docs/robot-host-devices.md](docs/robot-host-devices.md). The two CAN buses are
  `can_shoulder` and `can_odrive`, named by `.link` files there; the kernel's own `can0`
  and `can1` swap between boots.

## Pull all repositories with r2d2.repos

From the workspace root:

```bash
cd /home/davids/r2_ws
```

Import repositories into `src`:

```bash
vcs import src < src/r2_bringup/r2d2.repos
```

If repositories already exist and you want to update them:

```bash
vcs pull src
```

## Update from a changed r2d2.repos without losing local edits

If your `r2d2.repos` file was updated and you have uncommitted changes in sub-repositories,
stash local work first, then update, then restore your stashes.

Check which repos are dirty:

```bash
cd /home/davids/r2_ws
vcs custom src --git --args status --short
```

Stash uncommitted changes in all git repos under `src`:

```bash
vcs custom src --git --args stash push -u -m "pre-r2d2-repos-update"
```

Import the updated manifest and pull:

```bash
vcs import src < src/r2_bringup/r2d2.repos
vcs pull src
```

Restore stashed changes:

```bash
vcs custom src --git --args stash list
vcs custom src --git --args stash pop
```

If a repo has conflicts when popping its stash, resolve conflicts in that repo and commit as needed.

## Build

Always build from the workspace root with `--symlink-install`, after sourcing the workspace's `setup.bash`. That file is per-machine and not in git; see [Per-machine environment](#per-machine-environment) for its contents.

```bash
cd /home/davids/r2_ws
source ./setup.bash
colcon build --symlink-install
```

`setup.bash` sources the ROS install and then `install/setup.bash`. On the very first build, before `install/` exists, it reports that `install/setup.bash` is missing; this is expected.

After a build that adds new packages or executables, source `setup.bash` again in each shell you use:

```bash
source ./setup.bash
```

## Optional: build specific packages only

```bash
colcon build --symlink-install --packages-select r2_bringup r2_description r2_sim r2_web_interface ros2_roamadome ros2_shoulder_sensor
```

## Zenoh router

The workspace uses `rmw_zenoh_cpp`. Each machine runs its own Zenoh router, and every ROS node on that machine (including RViz and `ros2` CLI tools) connects to the local router on `tcp/localhost:7447`. A dev machine's router links to the robot's router, so nodes on the laptop can see the robot's topics.

```
laptop nodes ──> laptop router ──(connect)──> robot router <── robot nodes
```

### Per-machine environment

Each machine has a `setup.bash` in the workspace root (not in git) that selects the RMW and says whether this machine's router should connect to the robot.

Dev machine (laptop):

```bash
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
# Robot router for launch_zenoh_router.launch.py to connect to (leave unset on the robot)
export R2_ZENOH_CONNECT=tcp/r2-body.davidiansmith.ca:7447
source /opt/ros/jazzy/setup.bash
source install/setup.bash
```

Robot: the same, but without `R2_ZENOH_CONNECT`. Render it with
`make MACHINE=robot setup` rather than by hand; its working lines are
`export RMW_IMPLEMENTATION=rmw_zenoh_cpp`, `source /opt/ros/jazzy/setup.bash` and
`source install/setup.bash`. The robot's file once exported a stale
`ZENOH_ROUTER_CONFIG_URI` (see "Things to avoid"); delete anything else in it.

Source it from the workspace root, because it uses relative paths:

```bash
cd /home/davids/r2_ws
source ./setup.bash
```

### Start the router

Use the same command on every machine:

```bash
ros2 launch r2_bringup launch_zenoh_router.launch.py
```

The launch file starts `rmw_zenohd` with the stock router config shipped with `rmw_zenoh_cpp`. It applies its overrides through `ZENOH_CONFIG_OVERRIDE`, set only for the router process:

- `transport/link/tx/keep_alive=12`
- `connect/endpoints=[...]`, taken from the `connect` launch argument. This argument defaults to `$R2_ZENOH_CONNECT`; when it's empty, no connect endpoints are set.

To connect somewhere else for a single run, pass the argument. Separate multiple endpoints with commas:

```bash
ros2 launch r2_bringup launch_zenoh_router.launch.py connect:=tcp/192.168.1.50:7447
```

Start the router first and wait until it listens (`ss -ltn | grep 7447`) before launching
anything else on that machine: nodes launched earlier log `Unable to connect to a Zenoh
router`.

Check the link from the laptop: with both routers running, `ros2 topic list` should show the robot's topics.

### Things to avoid

- Don't export `ZENOH_CONFIG_OVERRIDE` in `setup.bash`. It applies to every Zenoh process, so each node would connect to the robot directly instead of to its local router.
- Don't keep a copied `DEFAULT_RMW_ZENOH_ROUTER_CONFIG.json5` or set `ZENOH_ROUTER_CONFIG_URI`. The launch file unsets `ZENOH_ROUTER_CONFIG_URI` so that the stock config, which is updated along with `rmw_zenoh_cpp`, is always used. Put any new router settings into the override list in `launch/launch_zenoh_router.launch.py`.
- Don't run node tests (`colcon test` of a package that starts nodes, a fake `/mood/state`
  publisher, mocks) in the dev container while it is connected to the robot. The laptop's
  or container's router peers with the robot's over WiFi, so the test's nodes (`dome_mock_t*`,
  `arbiter_test_*`, ...) are on the robot's graph: on 2026-10-23 that took the robot's router
  to 80-96 % of a core twice, with `Route reply: Query not found` and `Didn't receive final reply
  for query ... Timeout(600s)` on the peer link face, and it did not recover until it was restarted.
  Stop the container's router, or start it without `R2_ZENOH_CONNECT`, for the tests.

## Dome teleop: joystick and Foxglove

`dome_teleop.launch.py` (included by `launch_robot.launch.py` unless `dome_bench:=true`) runs
`dome_teleop_node` (teleop_twist_joy: the right trigger, axis 3, as `linear.x` on
`/cmd_vel_dome`, TwistStamped) and `dome_twist_converter`, which turns the command into the
`Float64MultiArray` on `/dome_controller/commands` that the dome velocity controller reads.

The converter also accepts a plain `geometry_msgs/Twist` on `/cmd_vel_dome_foxglove` from the
Foxglove Teleop panel (which cannot publish stamped messages), and arbitrates between the two
(`r2_bringup/dome_arbiter.py`, parameters under `dome_twist_converter` in
`config/dome_teleop.yaml`):

- **The joystick has precedence**: while its command is non-zero, and for `joystick_hold_s`
  (0.5 s) after it returns to zero. During that hold its zeros are forwarded, so releasing the
  trigger stops the dome even if Foxglove is pushing. Precedence is decided by the command
  value, not by who published last, because teleop_twist_joy publishes a zero on every joy
  message and would otherwise block Foxglove for ever.
- **Foxglove drives the dome otherwise**, while its latest message is younger than
  `foxglove_timeout_s` (0.5 s). The panel sends no stamp and no guaranteed zero on release, so
  that timeout is what stops the dome when the panel stops publishing or disconnects.
- The command is published from a 20 Hz timer, and one final zero when both sources are idle,
  so a source that goes quiet always results in a stop. A joystick stream older than
  `joystick_timeout_s` (joy_node gone) is ignored.

- **The personality is the lowest priority**: the dome arbiter of `r2_expression` publishes
  `geometry_msgs/TwistStamped` on `/dome/cmd/personality` (`angular.z`, rad/s, reliable, depth 1).
  It drives the dome only while the joystick and Foxglove are not, and only while its latest
  message (by arrival time, not stamp) is younger than `personality_timeout_s` (0.5 s). The
  converter works with no personality node on the graph. NaN and inf are treated as 0, with a
  warning at most once a minute.
- **Only the personality is capped**: |v| at most `personality_max_speed_rad_s` (2.0; the
  `personality_max_speed_rad_s` launch argument of `dome_teleop.launch.py` overrides it, so the
  robot and the sim can differ; `launch_robot.launch.py` and the sim's `launch_sim.launch.py` set it, default 2.0), and the change per tick at most `personality_max_accel_rad_s2`
  (6.0, so a 4 rad/s^2 profile from a 20 Hz clock out of phase with the converter's is never
  flagged) times the tick, counted from the value last *sent* by any source (a joystick release
  does not let the personality jump; a cold start to 2 rad/s takes about 0.3 s). Only increases in
  magnitude are limited: braking (a smaller value of the same sign, or 0) is applied at once, a
  reversal goes to 0 at once and then ramps up, and a timeout or takeover is immediate. The
  joystick and Foxglove are not capped here.
- **The dead-band floor**: the real dome's motor does nothing below about 0.44 rad/s positive and
  0.57 negative, so a ramp through those values would count as "commanded" while the motor gets
  0 %. When the last value sent is below `personality_min_speed_rad_s` (0.6; a launch argument
  of `dome_teleop.launch.py`) and the wanted magnitude is at or above it, the first step jumps
  to the floor with the wanted sign and the ramp starts from there; a reversal passes through 0
  and then jumps to the floor. `capped` in the status is true only when the speed cap clipped the
  value or the acceleration limit held it back by more than one tick's allowance, never for the
  floor jump alone.
- **Shutdown**: on SIGINT or SIGTERM (and on an exception) the converter publishes one final 0 on
  the output topic and gives it up to 0.2 s to leave before closing, because the
  ForwardCommandController holds its last command and the motor driver has no timeout. A second
  signal while closing is ignored. SIGKILL (or a power loss) cannot send a 0: the dome keeps
  turning at the last command, up to 2 rad/s (a risk carried in the phase 2 plan's risk list).
- **Status**: `astromech_msgs/DomeCommandStatus` on `/dome/cmd/status` (reliable, depth 1) with
  `source` (`idle`, `joystick`, `foxglove`, `personality`), `velocity_rad_s` (what was sent) and
  `capped`, on every source change and at `status_hz` (2.0) otherwise.

Parameters (`config/dome_teleop.yaml`): the joystick and Foxglove ones above, plus
`personality_topic`, `personality_field`, `personality_timeout_s`, `personality_max_speed_rad_s`,
`personality_max_accel_rad_s2`, `personality_min_speed_rad_s`, `status_topic`, `status_hz`.

Foxglove Teleop panel setup: topic `/cmd_vel_dome_foxglove`, message `geometry_msgs/Twist`,
map the left and right buttons to `angular.z` -1 and +1 (`foxglove_field`), publish rate about
10 Hz. The value is multiplied by `foxglove_scale` (rad/s per unit, 1.5 by default, like the
joystick's `scale_linear`). Positive values turn the joint positive: the plugin's `velocity_map`
handles the motor's inverted sign (`velocity_map.positive.percent_sign` -1, see the ros2_roamadome
README), so no scale needs a negative sign any more.

## Viewing R2 in Foxglove

`foxglove.launch.py` runs `foxglove_bridge`. With the live robot, run it on the dev machine
(the dev container's `foxglove` service does), not on the robot: `launch_robot.launch.py`
already publishes `/robot_description`, a complete `/joint_states` and `/tf`, and the bridge
serves the `package://` meshes from the dev machine's `r2_description`.

| argument | default | meaning |
| --- | --- | --- |
| `port` | `8765` | WebSocket port for the Foxglove app |
| `use_sim_time` | `false` | `true` with the sim: TF is stamped with `/clock` time, which a wall-clock bridge can't look up |
| `name` | `foxglove_bridge` | node name; give a second bridge on the same graph its own |

In the 3D panel, turn on `/robot_description`, set the display frame to `base_link` (or `odom`),
and under Scene set **Mesh up axis to Z**. R2's meshes are Z-up; with Foxglove's default (Y-up)
every mesh is drawn rotated 90°.

## Personality

`launch/personality.launch.py` starts the personality stack: `r2_affect` (the mood model: `/stimuli` in, `/mood/state` out) and, with `adapters` (default `true`), the three `r2_stimulus` adapters: `drive_stimulus` (from `/diff_cont/odom`: `being_driven`, `stopped`), `dome_stimulus` (from the dome joint state and command: `dome_pushed`) and `button_stimulus` (from `/dome/buttons/sequence`: `button_sequence`). The adapters only listen and publish `/stimuli`. `launch_robot.launch.py` and `r2_sim`'s `launch_sim.launch.py` both include it by default, with `use_sim_time` false and true. Pass `personality:=false` to either to leave it out.

It also starts the expression arbiters of `r2_expression` (`expression`, default `true`): `/led_arbiter` and `/magic_arbiter`, which own the dome's LEDs and Magic Panel and take claims through two services, `/expression/claim/led` and `/expression/claim/magic`. `express status` shows the four channels; the `express` CLI (`ros2 run r2_expression express ...`) is described in the `r2_expression` README. The arbiters talk to the dome device `/r2_dome`. In the sim, `dome_mock` is `true` and `r2_mocks`' dome mock stands in for the device; the sim's mock is `/dome_mock` (the sim launch files default `dome_mock_name` to it, and the arbiters' `device` follows), so it never collides with a real dome on the same graph. Pass `dome_mock_name:=r2_dome` only on a machine with no real dome, if you want the device's real name. An arbiter refuses to start when another node of its name is already on the graph.

| argument | default | meaning |
| --- | --- | --- |
| `use_sim_time` | `false` | `true` with the sim: the model's timers follow `/clock` and stop while Gazebo is paused |
| `affect_config` | `r2_affect`'s installed `config/affect.yaml` | the YAML to load |
| `adapters` | `true` | start the stimulus adapters of `r2_stimulus` (thresholds in its `config/stimulus.yaml`) |
| `stimulus_config` | `r2_stimulus`'s installed `config/stimulus.yaml` | the adapter thresholds (read at startup) |
| `rate_hz` | `5.0` | tick and `/mood/state` rate |
| `expression` | `true` | start the expression arbiters |
| `expression_config` | `r2_expression`'s installed `config/expression.yaml` | the arbiter config |
| `dome` | `true` | start the dome arbiter (`/dome_arbiter`) in `r2_expression` |
| `dome_mock` | `false` | start the dome mock of `r2_mocks` (the sim sets `true`) |
| `dome_mock_name` | `r2_dome` | node name, hence namespace, of the mock; the sim launch files pass `dome_mock` (the mock's `/dome/text/line*` and `/dome/audio/level` then live under `/dome_mock/dome/...`) |
| `device` | empty | device the arbiters use; empty means `/` + `dome_mock_name` with the mock, else `/r2_dome` |

The config lives in `r2_personality/r2_affect/config/affect.yaml`. With `--symlink-install` an edit is picked up by `ros2 service call /mood/reload_config std_srvs/srv/Trigger`, no restart needed. For the `mood` CLI (`mood watch`, `mood set`) see the `r2_affect` README; for the design see `docs/personality-architecture.md` in the r2_dev workspace.

## Sound on the Mac

R2's sound (phase 3, `r2_sound`) can be heard from the dev container on the Mac in two ways. Route 2 is a convenience: nothing in the stack or the tests needs it. The image changes (`libportaudio2`, `sounddevice` from pip, `libasound2-plugins`, `alsa-utils`, `/etc/asound.conf`) arrive with `make image` on the Mac, then Dev Containers: Rebuild Container (or `make up`). A rebuild's `vcs import` resets the `src/*` branches to `main`, so check the working branches out again afterwards (see `CLAUDE.md`).

### Route 1: files and `afplay` (no image rebuild needed)

The player's `wav` backend writes what it would have played to `/ws/.audio/out/`, which is the workspace's `.audio/out/` folder on the Mac (git-ignored). On the Mac:

```bash
afplay ~/path/to/r2_dev/.audio/out/<file>.wav
```

To hear each new file as it appears, run `tools/watch_out.sh` from the workspace root on the Mac. It polls once a second and `afplay`s every `.wav` newer than the last pass:

```bash
tools/watch_out.sh
```

### Route 2: live through PulseAudio on the Mac

The player's `sounddevice` backend plays through PortAudio's ALSA host API. In the image `/etc/asound.conf` makes the ALSA default the `pulse` plugin, so with `PULSE_SERVER` set the sound goes over TCP to a PulseAudio running on the Mac and out of its speakers (about 100 ms latency).

1. Install PulseAudio on the Mac: `brew install pulseaudio`.
2. Start it so the container can reach it, accepting the Docker address ranges:

   ```bash
   pulseaudio --exit-idle-time=-1 --daemonize=yes \
     --load="module-native-protocol-tcp auth-anonymous=1 auth-ip-acl=127.0.0.1;172.16.0.0/12;192.168.0.0/16;10.0.0.0/8"
   ```

   Or put the line in `~/.config/pulse/default.pa` so every start has it:

   ```
   .include /opt/homebrew/etc/pulse/default.pa
   load-module module-native-protocol-tcp auth-anonymous=1 auth-ip-acl=127.0.0.1;172.16.0.0/12;192.168.0.0/16;10.0.0.0/8
   ```

   (On an Intel Mac Homebrew's prefix is `/usr/local`.) Quote the `;` lists on a command line.
3. Check on the Mac: `pactl info` answers and `pactl list short sinks` shows the built-in output.
4. In the container (after the image rebuild) `compose.yaml` sets `PULSE_SERVER=tcp:host.docker.internal:4713` on the `dev` service. Docker Desktop makes the Mac reachable as `host.docker.internal`. Override `PULSE_SERVER` in `.env` for another address.
5. Container-side check, a 1 s 440 Hz tone, and the ALSA devices:

   ```bash
   python3 -c "import numpy as np, sounddevice as sd; sd.play(0.2*np.sin(2*np.pi*440*np.arange(22050)/22050), 22050); sd.wait()"
   aplay -L | head
   ```

   `aplay -L` should list `default` (the pulse plugin) near the top.

When it is silent:

- PulseAudio is not running on the Mac (`pactl info` fails); start it again, it does not survive a logout.
- The Mac firewall blocks it: allow incoming connections for `pulseaudio` (System Settings, Network, Firewall).
- `pactl list short sinks` on the Mac is empty or the Mac's output is muted or set to another device.
- The ALSA default is not pulse: `cat /etc/asound.conf` in the container should show the two `type pulse` lines, otherwise the image is old.
- `PULSE_SERVER` is unset or wrong in the container (`echo $PULSE_SERVER`). With it unset the tone fails with an error and the player falls back per its `backend` parameter.

## Joint state topics

- `/joint_states`: every joint, merged by `joint_state_publisher` from `/joint_broad/joint_states` and the dome servo device's `/dome/joint_states`.
- `/dome_state_broadcaster/joint_states`: only `dome_joint` (position), published by the `dome_state_broadcaster` controller at 10 Hz. It's for the dome servo device, which only needs the dome's rotation, refreshes its display at 4 Hz, and is too small to handle the full `/joint_states` message comfortably. The rate is `update_rate` under `dome_state_broadcaster.ros__parameters` in `config/my_controllers.yaml`. Keep it a divisor of the controller manager's 30 Hz; any other rate gives uneven spacing and a warning at startup.

## Notes

- The `r2d2.repos` file currently includes `astromech_msgs`, `ros_odrive`, and the R2 packages.
- If `vcs import` reports YAML key errors, check `src/r2_bringup/r2d2.repos` for typos in fields like `version`.
