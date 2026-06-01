from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([

        Node(
            package="l510_driver",
            executable="l510_node",
            name="l510_node",
            output="screen",
            parameters=[
                {"port": "/dev/ttyUSB0"},
                {"slave": 1},
                {"baudrate": 9600},
            ],
        ),

        Node(
            package="usb_camera_publisher",
            executable="usb_camera_node",
            name="usb_camera_node",
            output="screen",
            parameters=[
                {"camera_id": 0},
                {"width": 640},
                {"height": 480},
                {"fps": 15.0},
                {"publish_compressed": True},
                {"jpeg_quality": 60},
            ],
        ),

        Node(
            package="conveyor_remote_bridge",
            executable="remote_bridge_node",
            name="conveyor_remote_bridge",
            output="screen",
            parameters=[
                {"server_url": "http://10.42.0.177:8000"},
                {"poll_period": 0.5},
                {"send_camera": True},
            ],
        ),
    ])
