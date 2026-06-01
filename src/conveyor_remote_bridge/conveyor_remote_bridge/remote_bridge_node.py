#!/usr/bin/env python3

import json
import time

import requests
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from sensor_msgs.msg import CompressedImage


class ConveyorRemoteBridge(Node):
    def __init__(self):
        super().__init__("conveyor_remote_bridge")

        self.declare_parameter("server_url", "http://localhost:8000")
        self.declare_parameter("poll_period", 0.5)
        self.declare_parameter("send_camera", True)
        self.declare_parameter("output_cmd_topic", "/cmd/dashboard")

        self.server_url = self.get_parameter("server_url").value.rstrip("/")
        self.poll_period = float(self.get_parameter("poll_period").value)
        self.send_camera = bool(self.get_parameter("send_camera").value)
        self.output_cmd_topic = self.get_parameter("output_cmd_topic").value

        self.last_command_id = 0
        self.last_frame_time = 0.0
        self.frame_period = 0.07

        self.cmd_pub = self.create_publisher(String, self.output_cmd_topic, 10)

        self.telemetry_sub = self.create_subscription(
            String,
            "/conveyor/telemetry",
            self.telemetry_callback,
            10,
        )

        self.camera_sub = self.create_subscription(
            CompressedImage,
            "/camera/image/compressed",
            self.camera_callback,
            10,
        )

        self.timer = self.create_timer(self.poll_period, self.poll_commands)

        self.get_logger().info(f"Dashboard bridge conectado a {self.server_url}")
        self.get_logger().info(f"Comandos dashboard -> {self.output_cmd_topic}")

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
            self.get_logger().warn(f"No se pudieron leer comandos dashboard: {e}")
            return

        commands = data.get("commands", [])

        for item in commands:
            try:
                command_id = int(item.get("seq", 0))
                payload = self.normalize_cmd(item.get("cmd", {}))
            except Exception as e:
                self.get_logger().warn(f"Comando dashboard inválido: {e}")
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
                f"[DASHBOARD] Publicado en {self.output_cmd_topic}: {msg.data}"
            )

    def telemetry_callback(self, msg: String):
        try:
            telemetry = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warn("Telemetría local no es JSON válido")
            return

        try:
            response = requests.post(
                f"{self.server_url}/api/telemetry",
                json=telemetry,
                timeout=2.0,
            )
            response.raise_for_status()
        except Exception as e:
            self.get_logger().warn(f"No se pudo enviar telemetría al dashboard: {e}")

    def camera_callback(self, msg: CompressedImage):
        if not self.send_camera:
            return

        now = time.time()

        if now - self.last_frame_time < self.frame_period:
            return

        self.last_frame_time = now

        try:
            response = requests.post(
                f"{self.server_url}/api/frame",
                data=bytes(msg.data),
                headers={"Content-Type": "image/jpeg"},
                timeout=2.0,
            )
            response.raise_for_status()
        except Exception as e:
            self.get_logger().warn(f"No se pudo enviar frame al dashboard: {e}")


def main(args=None):
    rclpy.init(args=args)
    node = ConveyorRemoteBridge()

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
