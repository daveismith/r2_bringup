import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.substitutions import LaunchConfiguration, Command
from launch.actions import DeclareLaunchArgument
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

import xacro


def generate_launch_description():

    # Check if we're told to use sim time
    use_sim_time = LaunchConfiguration('use_sim_time')
    use_ros2_control = LaunchConfiguration('use_ros2_control')
    dome_bench = LaunchConfiguration('dome_bench')

    # Process the URDF file
    pkg_path = os.path.join(get_package_share_directory('r2_bringup'))
    xacro_file = os.path.join(pkg_path,'urdf','robot.urdf.xacro')
    robot_description_config = Command(['xacro ', xacro_file, ' use_ros2_control:=', use_ros2_control, ' sim_mode:=', use_sim_time, ' dome_bench:=', dome_bench])
    
    # Create a robot_state_publisher node
    # value_type=str keeps the URDF verbatim: unwrapped, launch YAML-parses it, which folds
    # it onto one line and fails outright if the text happens to look like YAML.
    params = {'robot_description': ParameterValue(robot_description_config, value_type=str), 'use_sim_time': use_sim_time}
    node_robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        output='screen',
        parameters=[params]
    )


    # Launch!
    return LaunchDescription([
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='false',
            description='Use sim time if true'),
        DeclareLaunchArgument(
            'use_ros2_control',
            default_value='true',
            description='Use ros2_control if true'),
        DeclareLaunchArgument(
            'dome_bench',
            default_value='false',
            description='Enable the dome bench raw drive service and telemetry if true'),

        node_robot_state_publisher
    ])
