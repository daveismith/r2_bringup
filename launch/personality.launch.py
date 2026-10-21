# Personality stack: the mood model (r2_affect), the stimulus adapters (r2_stimulus) and the
# expression arbiters (r2_expression: /led_arbiter and /magic_arbiter, claim services
# /expression/claim/led and /expression/claim/magic). With dome_mock:=true it also starts
# the dome device mock (r2_mocks) under dome_mock_name, and the arbiters talk to that.
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
from launch.substitutions import LaunchConfiguration, PythonExpression


def generate_launch_description():
    use_sim_time = LaunchConfiguration('use_sim_time')
    affect_config = LaunchConfiguration('affect_config')
    adapters = LaunchConfiguration('adapters')
    rate_hz = LaunchConfiguration('rate_hz')
    stimulus_config = LaunchConfiguration('stimulus_config')
    expression = LaunchConfiguration('expression')
    expression_config = LaunchConfiguration('expression_config')
    dome_mock = LaunchConfiguration('dome_mock')
    dome_mock_name = LaunchConfiguration('dome_mock_name')
    device = LaunchConfiguration('device')

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
            'rate_hz', default_value='5.0',
            description='r2_affect tick and /mood/state publish rate'),
        DeclareLaunchArgument(
            'expression', default_value='true',
            description='Start the expression arbiters (/led_arbiter, /magic_arbiter)'),
        DeclareLaunchArgument(
            'expression_config',
            default_value=os.path.join(
                get_package_share_directory('r2_expression'), 'config', 'expression.yaml'),
            description='Path of the expression.yaml to load'),
        DeclareLaunchArgument(
            'dome_mock', default_value='false',
            description='Start the dome device mock (r2_mocks) instead of relying on a real dome'),
        DeclareLaunchArgument(
            'dome_mock_name', default_value='r2_dome',
            description='Node name of the mock, hence its namespace /<name>/ (and, unless it is '
                        'r2_dome, the prefix of its /dome/text and /dome/audio topics). The sim '
                        'passes dome_mock; r2_dome only on a machine with no real dome'),
        DeclareLaunchArgument(
            'device', default_value='',
            description="Dome device the arbiters talk to; empty: '/' + dome_mock_name with "
                        'dome_mock:=true, else /r2_dome'),
    ]

    device_ns = PythonExpression([
        "'", device, "' or ('/' + '", dome_mock_name, "' if '", dome_mock,
        "'.lower() == 'true' else '/r2_dome')"])

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

    arbiters = GroupAction(scoped=True, condition=IfCondition(expression), actions=[
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(
                get_package_share_directory('r2_expression'), 'launch', 'expression.launch.py')),
            launch_arguments={
                'use_sim_time': use_sim_time,
                'config': expression_config,
                'device': device_ns,
            }.items(),
        )])

    mock = GroupAction(scoped=True, condition=IfCondition(dome_mock), actions=[
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(
                get_package_share_directory('r2_mocks'), 'launch', 'dome_mock.launch.py')),
            launch_arguments={
                'use_sim_time': use_sim_time,
                'node_name': dome_mock_name,
            }.items(),
        )])

    return LaunchDescription(declared + [affect, stimulus_adapters, arbiters, mock])
