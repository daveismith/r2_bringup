from launch import LaunchDescription
from launch_ros.actions import Node
from launch.substitutions import LaunchConfiguration
from launch.actions import DeclareLaunchArgument

import os
from ament_index_python.packages import get_package_share_directory

def generate_launch_description():
    package_name = 'r2_bringup'
    use_sim_time = LaunchConfiguration('use_sim_time')

    dome_params = os.path.join(get_package_share_directory(package_name),'config','dome_teleop.yaml')

    dome_teleop_node = Node(
            package='teleop_twist_joy',
            executable='teleop_node',
            name='dome_teleop_node',
            parameters=[dome_params, {'use_sim_time': use_sim_time}],
            remappings=[('/cmd_vel','/cmd_vel_dome')]
         )

    dome_twist_converter = Node(
            package=package_name,
            executable='dome_twist_converter',
            name='dome_twist_converter',
            parameters=[{'use_sim_time': use_sim_time}],
            #remappings=[('/cmd_vel_', '/cmd_vel_dome')],
            output='screen'
         )

    return LaunchDescription([
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='false',
            description='Use sim time if true'),
        dome_teleop_node,
        dome_twist_converter
    ])
