#!/usr/bin/env python3

import json

import requests
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class VoiceRemoteBridge(Node):
    def __init__(self):
        super().__init__("voice_remote_bridge")

        self.declare_parameter("server_url", "http://localhost:8010")
        self.declare_parameter("poll_period", 0.5)
        self.declare_parameter("output_cmd_topic", "/cmd/voice")

        self.server_url = self.get_parameter("server_url").value.rstrip("/")
        self.poll_period = float(self.get_parameter("poll_period").value)
        self.output_cmd_topic = self.get_parameter("output_cmd_topic").value

        self.last_command_id = 0

        self.cmd_pub = self.create_publisher(String, self.output_cmd_topic, 10)

        self.timer = self.create_timer(self.poll_period, self.poll_commands)

        self.get_logger().info(f"Voice bridge conectado a {self.server_url}")
        self.get_logger().info(f"Comandos voz -> {self.output_cmd_topic}")

    def normalize_cmd(self, payload):
        if not isinstance(payload, dict):
            return {}

        cmd = dict(payload)

        speed = None
        for key in ("speed_hz", "hz", "speed", "frequency", "freq_hz"):
            if key in cmd and cmd[key] is not None:
                try:
                    speed = float(cmd[key])
                    break
                except Exception:
                    pass

        if speed is not None:
            speed = max(0.0, min(60.0, speed))
            cmd["speed_hz"] = speed
            cmd["hz"] = speed

        return cmd

    def poll_commands(self):
        try:
            response = requests.get(
                f"{self.server_url}/api/commands",
                params={"after": self.last_command_id},
                timeout=2.0,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            self.get_logger().warn(f"No se pudieron leer comandos de voz: {e}")
            return

        commands = data.get("commands", [])

        for item in commands:
            try:
                command_id = int(item.get("seq", 0))
                payload = self.normalize_cmd(item.get("cmd", {}))
            except Exception as e:
                self.get_logger().warn(f"Comando de voz inválido: {e}")
                continue

            if command_id <= self.last_command_id:
                continue

            if not payload:
                continue

            msg = String()
            msg.data = json.dumps(payload)
            self.cmd_pub.publish(msg)

            self.last_command_id = command_id

            self.get_logger().info(
                f"[VOICE] Publicado en {self.output_cmd_topic}: {msg.data}"
            )


def main(args=None):
    rclpy.init(args=args)
    node = VoiceRemoteBridge()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
