from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, SetEnvironmentVariable, UnsetEnvironmentVariable
from launch.substitutions import EnvironmentVariable, LaunchConfiguration
from launch_ros.actions import Node


# The router runs with the stock rmw_zenoh config; only these keys are overridden.
# Set ZENOH_CONFIG_OVERRIDE here (scoped to this launch) rather than in setup.bash,
# since it would otherwise also apply to every node's session config.
KEEP_ALIVE = 12


def router_config_override(context):
    overrides = [f'transport/link/tx/keep_alive={KEEP_ALIVE}']

    connect = LaunchConfiguration('connect').perform(context)
    if connect:
        endpoints = ','.join(f'"{e.strip()}"' for e in connect.split(',') if e.strip())
        overrides.append(f'connect/endpoints=[{endpoints}]')

    return [SetEnvironmentVariable(name='ZENOH_CONFIG_OVERRIDE', value=';'.join(overrides))]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            'connect',
            # Per-machine default from setup.bash: unset on the robot, set on dev machines
            default_value=EnvironmentVariable('R2_ZENOH_CONNECT', default_value=''),
            description='Comma separated router endpoints to connect to (default: $R2_ZENOH_CONNECT). '
                        'Leave empty on the robot; on a dev machine use e.g. '
                        'tcp/r2-body.davidiansmith.ca:7447'),
        # Use the packaged default router config rather than a local copy
        UnsetEnvironmentVariable(name='ZENOH_ROUTER_CONFIG_URI'),
        OpaqueFunction(function=router_config_override),
        Node(
            package="rmw_zenoh_cpp",
            executable="rmw_zenohd",
            output="screen"
        )
    ])
