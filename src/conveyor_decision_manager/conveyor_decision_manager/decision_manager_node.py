#!/usr/bin/env python3

import json
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class ConveyorDecisionManager(Node):
    def __init__(self):
        super().__init__("conveyor_decision_manager")

        self.declare_parameter("gui_topic", "/cmd/gui")
        self.declare_parameter("dashboard_topic", "/cmd/dashboard")
        self.declare_parameter("voice_topic", "/cmd/voice")
        self.declare_parameter("output_topic", "/conveyor/cmd")
        self.declare_parameter("priority_window_sec", 2.0)

        self.gui_topic = self.get_parameter("gui_topic").value
        self.dashboard_topic = self.get_parameter("dashboard_topic").value
        self.voice_topic = self.get_parameter("voice_topic").value
        self.output_topic = self.get_parameter("output_topic").value
        self.priority_window_sec = float(self.get_parameter("priority_window_sec").value)

        self.priority = {
            "voice": 1,
            "dashboard": 2,
            "gui": 3,
        }

        self.last_accepted_source = None
        self.last_accepted_time = 0.0

        self.cmd_pub = self.create_publisher(String, self.output_topic, 10)

        self.create_subscription(
            String,
            self.gui_topic,
            lambda msg: self.handle_command(msg, "gui"),
            10,
        )

        self.create_subscription(
            String,
            self.dashboard_topic,
            lambda msg: self.handle_command(msg, "dashboard"),
            10,
        )

        self.create_subscription(
            String,
            self.voice_topic,
            lambda msg: self.handle_command(msg, "voice"),
            10,
        )

        self.get_logger().info("Decision Manager iniciado")
        self.get_logger().info(f"GUI       -> {self.gui_topic} prioridad 3")
        self.get_logger().info(f"Dashboard -> {self.dashboard_topic} prioridad 2")
        self.get_logger().info(f"Voice     -> {self.voice_topic} prioridad 1")
        self.get_logger().info(f"Salida    -> {self.output_topic}")

    def normalize_cmd(self, cmd):
        if not isinstance(cmd, dict):
            return {}

        normalized = dict(cmd)

        action = str(normalized.get("action", "")).lower().strip()
        normalized["action"] = action

        speed = None

        for key in ("speed_hz", "hz", "speed", "frequency", "freq_hz"):
            if key in normalized and normalized[key] is not None:
                try:
                    speed = float(normalized[key])
                    break
                except Exception:
                    pass

        if speed is not None:
            speed = max(0.0, min(60.0, speed))
            normalized["speed_hz"] = speed
            normalized["hz"] = speed

        clean_cmd = {}

        if action:
            clean_cmd["action"] = action

        if speed is not None:
            clean_cmd["speed_hz"] = speed
            clean_cmd["hz"] = speed

        return clean_cmd

    def should_accept(self, source, cmd):
        action = cmd.get("action", "")

        if action in ("emergency_stop", "stop"):
            return True, "stop/emergency_stop permitido"

        now = time.time()

        if self.last_accepted_source is None:
            return True, "primer comando"

        elapsed = now - self.last_accepted_time

        if elapsed >= self.priority_window_sec:
            return True, "ventana expirada"

        incoming_priority = self.priority.get(source, 0)
        last_priority = self.priority.get(self.last_accepted_source, 0)

        if incoming_priority >= last_priority:
            return True, "prioridad igual o superior"

        return False, f"bloqueado por {self.last_accepted_source}"

    def handle_command(self, msg, source):
        try:
            raw_cmd = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warn(f"[{source}] JSON inválido: {msg.data}")
            return

        cmd = self.normalize_cmd(raw_cmd)

        if not cmd.get("action"):
            self.get_logger().warn(f"[{source}] Comando sin action: {raw_cmd}")
            return

        accept, reason = self.should_accept(source, cmd)

        if not accept:
            self.get_logger().warn(
                f"[RECHAZADO] source={source} reason={reason} cmd={cmd}"
            )
            return

        out = String()
        out.data = json.dumps(cmd)
        self.cmd_pub.publish(out)

        self.last_accepted_source = source
        self.last_accepted_time = time.time()

        log_cmd = dict(cmd)
        log_cmd["source"] = source
        log_cmd["decision_timestamp"] = self.last_accepted_time

        self.get_logger().info(
            f"[ACEPTADO] source={source} reason={reason} -> {json.dumps(log_cmd)}"
        )


def main(args=None):
    rclpy.init(args=args)
    node = ConveyorDecisionManager()

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
