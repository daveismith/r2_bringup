# Personality stack: the mood model (r2_affect) and, from step 7, the stimulus adapters.
#
# launch_robot.launch.py and r2_sim's launch_sim.launch.py both include this file under
# their `personality` argument (default true), with use_sim_time false and true. With the
# sim, use_sim_time must be true so the model's timers follow /clock and stop when Gazebo
# is paused.
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    use_sim_time = LaunchConfiguration('use_sim_time')
    affect_config = LaunchConfiguration('affect_config')
    adapters = LaunchConfiguration('adapters')
    rate_hz = LaunchConfiguration('rate_hz')
    stimulus_config = LaunchConfiguration('stimulus_config')

    declared = [
        DeclareLaunchArgument(
            'use_sim_time', default_value='false',
            description='Use sim time if true (required with the sim)'),
        DeclareLaunchArgument(
            'affect_config',
            default_value=os.path.join(
                get_package_share_directory('r2_affect'), 'config', 'affect.yaml'),
            description='Path of the affect.yaml to load (reload with /mood/reload_config)'),
        DeclareLaunchArgument(
            'adapters', default_value='true',
            description='Start the stimulus adapters (drive, dome, buttons) of r2_stimulus'),
        DeclareLaunchArgument(
            'stimulus_config',
            default_value=os.path.join(
                get_package_share_directory('r2_stimulus'), 'config', 'stimulus.yaml'),
            description='Path of the stimulus.yaml with the adapter thresholds'),
        DeclareLaunchArgument(
            'rate_hz', default_value='10.0',
            description='r2_affect tick and /mood/state publish rate'),
    ]

    # Each include is scoped: affect.launch.py and adapters.launch.py both declare an
    # argument called `config`, and an unscoped include would leak one into the other.
    affect = GroupAction(scoped=True, actions=[IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory('r2_affect'), 'launch', 'affect.launch.py')),
        launch_arguments={
            'use_sim_time': use_sim_time,
            'config': affect_config,
            'rate_hz': rate_hz,
        }.items(),
    )])

    stimulus_adapters = GroupAction(scoped=True, condition=IfCondition(adapters), actions=[
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(
                get_package_share_directory('r2_stimulus'), 'launch', 'adapters.launch.py')),
            launch_arguments={
                'use_sim_time': use_sim_time,
                'config': stimulus_config,
            }.items(),
        )])

    return LaunchDescription(declared + [affect, stimulus_adapters])
