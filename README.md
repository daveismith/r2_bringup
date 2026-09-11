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

Always build from the workspace root:

```bash
cd /home/davids/r2_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
```

After a successful build, source the workspace overlay:

```bash
source install/setup.bash
```

## Optional: build specific packages only

```bash
colcon build --symlink-install --packages-select r2_bringup r2_description r2_sim r2_web_interface ros2_roamadome ros2_shoulder_sensor
```

## Notes

- The `r2d2.repos` file currently includes `astromech_msgs`, `ros_odrive`, and the R2 packages.
- If `vcs import` reports YAML key errors, check `src/r2_bringup/r2d2.repos` for typos in fields like `version`.
