import os

from ament_index_python.packages import get_package_share_directory


from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, SetEnvironmentVariable, TimerAction
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch.actions import RegisterEventHandler
from launch.event_handlers import OnProcessStart, OnProcessExit
from launch_ros.actions import Node



def generate_launch_description():


    # Include the robot_state_publisher launch file, provided by our own package. Force sim time to be enabled
    # !!! MAKE SURE YOU SET THE PACKAGE NAME CORRECTLY !!!

    # dome_bench:=true makes the RoamADome hardware offer its raw bench drive service and
    # telemetry, and leaves the dome to the bench tooling: no dome_controller, no dome teleop.
    dome_bench = LaunchConfiguration('dome_bench')
    dome_bench_arg = DeclareLaunchArgument(
        'dome_bench',
        default_value='false',
        description='Dome bench diagnostics: enable bench drive service, skip dome controller and teleop')

    package_name='r2_bringup' #<--- CHANGE ME
    web_package_name = 'r2_web_interface'

    rsp = IncludeLaunchDescription(
                PythonLaunchDescriptionSource([os.path.join(
                    get_package_share_directory(package_name),'launch','rsp.launch.py'
                )]), launch_arguments={'use_sim_time': 'false', 'use_ros2_control': 'true',
                                  'dome_bench': dome_bench}.items()
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
                    controller_params_file],
        #arguments=['--ros-args', '--log-level', 'DEBUG'],
    )

    delayed_controller_manager = TimerAction(period=3.0, actions=[controller_manager])

    dome_teleop = IncludeLaunchDescription(
                PythonLaunchDescriptionSource([os.path.join(
                    get_package_share_directory(package_name),'launch','dome_teleop.launch.py'
                )]), launch_arguments={'use_sim_time': 'false'}.items(),
                condition=UnlessCondition(dome_bench)
    )

    web_interface = IncludeLaunchDescription(
                PythonLaunchDescriptionSource([os.path.join(
                    get_package_share_directory(web_package_name),'launch','web_interface.launch.py'
                )]), launch_arguments={'use_sim_time': 'false', 'robot_mode': 'real'}.items()
    )

    diff_drive_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["diff_cont"],
    )

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
        condition=UnlessCondition(dome_bench),
    )

    dome_state_broadcaster_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["dome_state_broadcaster"],
    )

    delayed_joint_broad_spawner = RegisterEventHandler(
        event_handler=OnProcessStart(
            target_action=controller_manager,
            on_start=[
                joint_broad_spawner
                ],
        )
    )

    delay_robot_controller_spawner_after_joint_state_broadcaster_spawner = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=joint_broad_spawner,
            on_exit=[
                diff_drive_spawner,
                dome_controller_spawner,
                dome_state_broadcaster_spawner,
            ],
        )
    )


    joint_states = IncludeLaunchDescription(
                PythonLaunchDescriptionSource([os.path.join(
                    get_package_share_directory(package_name),'launch','joint_states.launch.py'
                )]), launch_arguments={'use_sim_time': 'false'}.items()
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



    # Dome bench diagnostics node (ros2_roamadome). It finds the RoamADome hardware
    # node by name: the ros2_control block "RoamADome" runs as /roamadome. Start
    # sweeps with `ros2 service call /roamadome_bench/start_sensor_sweep std_srvs/srv/Trigger`
    # (or start_speed_sweep), stop one with /roamadome_bench/abort and wait for it to
    # finish before stopping the launch: on Ctrl-C the controller manager deactivates at
    # the same time (sending :DPR0), so the node can stop the dome but usually cannot
    # restore the speed settings it changed (see settings_before.json in the run
    # directory). The longer sigterm_timeout lets it write its partial results first.
    dome_bench_node = Node(
        package='ros2_roamadome',
        executable='roamadome_bench',
        name='roamadome_bench',
        output='screen',
        parameters=[{'hardware_node': 'roamadome'}],
        sigterm_timeout='15',
        condition=IfCondition(dome_bench),
    )

    # Launch them all!
    return LaunchDescription([
        dome_bench_arg,
        rsp,
        joystick,
        twist_mux,
        delayed_controller_manager,
        #delayed_diff_drive_spawner,
        delayed_joint_broad_spawner,
        delay_robot_controller_spawner_after_joint_state_broadcaster_spawner,
        joint_states,
        dome_teleop,
        dome_bench_node,
        web_interface
    ])
