from launch import LaunchDescription
from launch.actions import SetEnvironmentVariable
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        SetEnvironmentVariable(name='ZENOH_ROUTER_CONFIG_URI', value='/home/pi/r2_ws/DEFAULT_RMW_ZENOH_ROUTER_CONFIG.json5'),
        Node(
            package="rmw_zenoh_cpp",
            executable="rmw_zenohd",
            parameters=[],
            output="screen"
        )
    ])