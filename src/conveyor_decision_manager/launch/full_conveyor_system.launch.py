from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, SetEnvironmentVariable
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    voice_server_ip = LaunchConfiguration("voice_server_ip")

    return LaunchDescription([
        DeclareLaunchArgument(
            "voice_server_ip",
            default_value="192.168.50.3",
            description="IP de la laptop donde corre el servidor del asistente de voz",
        ),

        SetEnvironmentVariable("DISPLAY", ":0"),
        SetEnvironmentVariable("XAUTHORITY", "/home/jetsonherbie/.Xauthority"),

        Node(
            package="l510_driver",
            executable="l510_node",
            name="l510_node",
            output="screen",
            parameters=[
                {"port": "/dev/l510_rs485"},
                {"slave": 1},
                {"baudrate": 9600},
            ],
        ),

        Node(
            package="conveyor_decision_manager",
            executable="decision_manager_node",
            name="conveyor_decision_manager",
            output="screen",
            parameters=[
                {"gui_topic": "/cmd/gui"},
                {"dashboard_topic": "/cmd/dashboard"},
                {"voice_topic": "/cmd/voice"},
                {"output_topic": "/conveyor/cmd"},
                {"priority_window_sec": 2.0},
            ],
        ),

        Node(
            package="conveyor_hmi",
            executable="touch_hmi_node",
            name="touch_hmi_node",
            output="screen",
            parameters=[
                {"cmd_topic": "/cmd/gui"},
                {"telemetry_topic": "/conveyor/telemetry"},
            ],
        ),

        Node(
            package="conveyor_remote_bridge",
            executable="remote_bridge_node",
            name="dashboard_remote_bridge",
            output="screen",
            parameters=[
                {"server_url": "http://192.168.50.1:8000"},
                {"output_cmd_topic": "/cmd/dashboard"},
                {"poll_period": 0.5},
                {"send_camera": True},
            ],
        ),

        Node(
            package="voice_remote_bridge",
            executable="voice_bridge_node",
            name="voice_remote_bridge",
            output="screen",
            parameters=[
                {"server_url": ["http://", voice_server_ip, ":8010"]},
                {"output_cmd_topic": "/cmd/voice"},
                {"poll_period": 0.5},
            ],
        ),
    ])
