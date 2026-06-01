from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    l510_node = Node(
        package="l510_driver",
        executable="l510_node",
        name="l510_node",
        output="screen",
        parameters=[
            {
                "port": "/dev/ttyUSB0",
                "slave": 1,
                "baudrate": 9600,
                "initial_speed": 10.0,
                "telemetry_period": 0.5,
            }
        ],
    )

    camera_node = Node(
        package="conveyor_camera",
        executable="webcam_node",
        name="webcam_node",
        output="screen",
        parameters=[
            {
                "camera_id": 0,
                "fps": 20.0,
                "jpeg_quality": 80,
            }
        ],
    )

    joy_node = Node(
        package="joy",
        executable="joy_node",
        name="joy_node",
        output="screen",
    )

    joy_mapper_node = Node(
        package="conveyor_joystick",
        executable="joy_mapper_node",
        name="joy_mapper_node",
        output="screen",
    )

    return LaunchDescription([
        l510_node,
        camera_node,
        joy_node,
        joy_mapper_node,
    ])
