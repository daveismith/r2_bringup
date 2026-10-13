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

Robot: the same, but without `R2_ZENOH_CONNECT`.

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

Check the link from the laptop: with both routers running, `ros2 topic list` should show the robot's topics.

### Things to avoid

- Don't export `ZENOH_CONFIG_OVERRIDE` in `setup.bash`. It applies to every Zenoh process, so each node would connect to the robot directly instead of to its local router.
- Don't keep a copied `DEFAULT_RMW_ZENOH_ROUTER_CONFIG.json5` or set `ZENOH_ROUTER_CONFIG_URI`. The launch file unsets `ZENOH_ROUTER_CONFIG_URI` so that the stock config, which is updated along with `rmw_zenoh_cpp`, is always used. Put any new router settings into the override list in `launch/launch_zenoh_router.launch.py`.

## Joint state topics

- `/joint_states`: every joint, merged by `joint_state_publisher` from `/joint_broad/joint_states` and the dome servo device's `/dome/joint_states`.
- `/dome_state_broadcaster/joint_states`: only `dome_joint` (position), published by the `dome_state_broadcaster` controller at 10 Hz. It's for the dome servo device, which only needs the dome's rotation, refreshes its display at 4 Hz, and is too small to handle the full `/joint_states` message comfortably. The rate is `update_rate` under `dome_state_broadcaster.ros__parameters` in `config/my_controllers.yaml`. Keep it a divisor of the controller manager's 30 Hz; any other rate gives uneven spacing and a warning at startup.

## Notes

- The `r2d2.repos` file currently includes `astromech_msgs`, `ros_odrive`, and the R2 packages.
- If `vcs import` reports YAML key errors, check `src/r2_bringup/r2d2.repos` for typos in fields like `version`.
