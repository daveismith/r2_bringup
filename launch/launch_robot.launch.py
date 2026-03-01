import os

from ament_index_python.packages import get_package_share_directory


from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, SetEnvironmentVariable, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command
from launch.actions import RegisterEventHandler
from launch.event_handlers import OnProcessStart
from launch_ros.actions import Node
from math import radians



def generate_launch_description():


    # Include the robot_state_publisher launch file, provided by our own package. Force sim time to be enabled
    # !!! MAKE SURE YOU SET THE PACKAGE NAME CORRECTLY !!!

    package_name='r2_bringup' #<--- CHANGE ME

    rsp = IncludeLaunchDescription(
                PythonLaunchDescriptionSource([os.path.join(
                    get_package_share_directory(package_name),'launch','rsp.launch.py'
                )]), launch_arguments={'use_sim_time': 'false', 'use_ros2_control': 'true'}.items()
    )

    joystick = IncludeLaunchDescription(
                PythonLaunchDescriptionSource([os.path.join(
                    get_package_share_directory(package_name),'launch','joystick.launch.py'
                )])
    )

    twist_mux_params = os.path.join(get_package_share_directory(package_name),'config','twist_mux.yaml')
    twist_mux = Node(
            package="twist_mux",
            executable="twist_mux",
            parameters=[twist_mux_params],
            remappings=[('/cmd_vel_out','/diff_cont/cmd_vel')]
        )

    robot_description = Command(['ros2 param get --hide-type /robot_state_publisher robot_description'])

    controller_params_file = os.path.join(get_package_share_directory(package_name),'config','my_controllers.yaml')

    controller_manager = Node(
        package="controller_manager",
        executable="ros2_control_node",
        parameters=[{'robot_description': robot_description},
                    controller_params_file]
    )

    delayed_controller_manager = TimerAction(period=3.0, actions=[controller_manager])

    dome_teleop = IncludeLaunchDescription(
                PythonLaunchDescriptionSource([os.path.join(
                    get_package_share_directory(package_name),'launch','dome_teleop.launch.py'
                )]), launch_arguments={'use_sim_time': 'false'}.items()
    )

    #diff_drive_spawner = Node(
    #    package="controller_manager",
    #    executable="spawner",
    #    arguments=["diff_cont"],
    #)

    #delayed_diff_drive_spawner = RegisterEventHandler(
    #    event_handler=OnProcessStart(
    #        target_action=controller_manager,
    #        on_start=[diff_drive_spawner],
    #    )
    #)

    joint_broad_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["joint_broad"],
    )

    dome_controller_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["dome_controller"],
    )


    delayed_joint_broad_spawner = RegisterEventHandler(
        event_handler=OnProcessStart(
            target_action=controller_manager,
            on_start=[
                dome_controller_spawner,
                joint_broad_spawner],
        )
    )



    joint_state_publisher = Node(
        package="joint_state_publisher",
        executable="joint_state_publisher",
        output='screen',
        parameters=[
            {
                'source_list': ['/joint_broad/joint_states', '/left_shoulder/position', '/right_shoulder/position'],
                'zeros': {
                    'right_shoulder_joint': radians(0),
                    'right_ankle_joint': radians(0),
                    'left_shoulder_joint': radians(0),
                    'left_ankle_joint': radians(0),
                }
            }]
    )

    # Code for delaying a node (I haven't tested how effective it is)
    # 
    # First add the below lines to imports
    # from launch.actions import RegisterEventHandler
    # from launch.event_handlers import OnProcessExit
    #
    # Then add the following below the current diff_drive_spawner
    # delayed_diff_drive_spawner = RegisterEventHandler(
    #     event_handler=OnProcessExit(
    #         target_action=spawn_entity,
    #         on_exit=[diff_drive_spawner],
    #     )
    # )
    #
    # Replace the diff_drive_spawner in the final return with delayed_diff_drive_spawner



    # Launch them all!
    return LaunchDescription([
        rsp,
        joystick,
        twist_mux,
        delayed_controller_manager,
        #delayed_diff_drive_spawner,
        delayed_joint_broad_spawner,
        joint_state_publisher,
        dome_teleop
    ])
