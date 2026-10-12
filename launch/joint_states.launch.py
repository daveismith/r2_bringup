from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from math import radians


def generate_launch_description():

    use_sim_time = LaunchConfiguration('use_sim_time')

    # joint_broad publishes on /joint_broad/joint_states (use_local_topics). This node
    # merges it with the URDF (filling in mimic joints) and publishes /joint_states.
    joint_state_publisher = Node(
        package="joint_state_publisher",
        executable="joint_state_publisher",
        output='screen',
        parameters=[
            {
                #'source_list': ['/joint_broad/joint_states', '/left_shoulder/position', '/right_shoulder/position'],
                'source_list': ['/joint_broad/joint_states'],
                'zeros': {
                    'right_shoulder_joint': radians(0),
                    'right_ankle_joint': radians(0),
                    'left_shoulder_joint': radians(0),
                    'left_ankle_joint': radians(0),
                },
                'use_sim_time': ParameterValue(use_sim_time, value_type=bool),
            }]
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='false',
            description='Use sim time if true'),
        joint_state_publisher
    ])
