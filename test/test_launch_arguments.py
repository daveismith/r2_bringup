"""Launch-argument tests (no ROS graph): the files import and declare what the docs say."""

import importlib.util
import os

from launch.actions import DeclareLaunchArgument

LAUNCH_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'launch')


def declared(name):
    spec = importlib.util.spec_from_file_location(
        name.replace('.', '_'), os.path.join(LAUNCH_DIR, name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {
        a.name: a for a in module.generate_launch_description().entities
        if isinstance(a, DeclareLaunchArgument)}


def default(arg):
    return ''.join(t.text for t in arg.default_value)


def test_personality_declares_dome():
    args = declared('personality.launch.py')
    assert default(args['dome']) == 'true'
    assert 'dome_arbiter' in args['dome'].description


def test_robot_declares_personality_max_speed():
    args = declared('launch_robot.launch.py')
    assert default(args['personality_max_speed_rad_s']) == '2.0'


def test_personality_declares_sound():
    args = declared('personality.launch.py')
    expected = {'sound': 'true', 'sound_backend': 'sounddevice', 'sounds_dir': '/sounds',
                'sound_device': '', 'dome_level_topic': '/dome/audio/level'}
    for name, value in expected.items():
        assert default(args[name]) == value, name
    assert default(args['sound_catalogue']).endswith('config/clips.yaml')


def test_robot_declares_sound():
    args = declared('launch_robot.launch.py')
    assert default(args['sounds_dir']) == '/home/pi/sounds'
    assert default(args['sound_device']) == 'USB'
