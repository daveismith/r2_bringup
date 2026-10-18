from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


# foxglove_bridge for viewing R2 in the Foxglove app. It needs no robot-side changes: the
# robot (launch_robot) or the sim (launch_sim) already publishes /robot_description, a
# complete /joint_states and /tf, and the bridge serves the package:// meshes from this
# machine's r2_description.
#
# With the live robot, run this on the dev machine (the dev container's `foxglove`
# service does). With the sim, use_sim_time must be true: TF is stamped with /clock time,
# and the bridge passes that clock to Foxglove so transforms are looked up at sim time.
def generate_launch_description():
    bridge = Node(
        package='foxglove_bridge',
        executable='foxglove_bridge',
        name=LaunchConfiguration('name'),
        output='screen',
        parameters=[{
            'address': '0.0.0.0',
            'port': ParameterValue(LaunchConfiguration('port'), value_type=int),
            'use_sim_time': ParameterValue(LaunchConfiguration('use_sim_time'), value_type=bool),
        }]
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'port',
            default_value='8765',
            description='WebSocket port for the Foxglove app'),
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='false',
            description='Use sim time if true (required with the sim)'),
        DeclareLaunchArgument(
            'name',
            default_value='foxglove_bridge',
            description='Node name; give a second bridge on the same graph its own'),
        bridge
    ])
