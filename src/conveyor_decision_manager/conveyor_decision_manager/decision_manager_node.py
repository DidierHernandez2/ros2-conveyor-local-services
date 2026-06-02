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
        self.declare_parameter("deadman_topic", "/safety/deadman")
        self.declare_parameter("auth_topic", "/auth/face_role")
        self.declare_parameter("output_topic", "/conveyor/cmd")

        self.declare_parameter("priority_window_sec", 2.0)
        self.declare_parameter("deadman_timeout_sec", 1.0)
        self.declare_parameter("auth_timeout_sec", 2.0)
        self.declare_parameter("require_deadman", True)

        self.gui_topic = self.get_parameter("gui_topic").value
        self.dashboard_topic = self.get_parameter("dashboard_topic").value
        self.voice_topic = self.get_parameter("voice_topic").value
        self.deadman_topic = self.get_parameter("deadman_topic").value
        self.auth_topic = self.get_parameter("auth_topic").value
        self.output_topic = self.get_parameter("output_topic").value

        self.priority_window_sec = float(self.get_parameter("priority_window_sec").value)
        self.deadman_timeout_sec = float(self.get_parameter("deadman_timeout_sec").value)
        self.auth_timeout_sec = float(self.get_parameter("auth_timeout_sec").value)
        self.require_deadman = bool(self.get_parameter("require_deadman").value)

        self.priority = {
            "voice": 1,
            "dashboard": 2,
            "gui": 3,
        }

        self.last_accepted_source = None
        self.last_accepted_time = 0.0

        self.deadman_pressed = False
        self.last_deadman_time = 0.0
        self.deadman_stop_sent = False

        self.face_role = "none"
        self.face_name = "none"
        self.face_detected = False
        self.face_confidence = 0.0
        self.last_auth_time = 0.0

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

        self.create_subscription(
            String,
            self.deadman_topic,
            self.deadman_callback,
            10,
        )

        self.create_subscription(
            String,
            self.auth_topic,
            self.auth_callback,
            10,
        )

        self.safety_timer = self.create_timer(0.1, self.safety_watchdog)

        self.get_logger().info("Decision Manager iniciado")
        self.get_logger().info(f"GUI       -> {self.gui_topic} prioridad 3")
        self.get_logger().info(f"Dashboard -> {self.dashboard_topic} prioridad 2")
        self.get_logger().info(f"Voice     -> {self.voice_topic} prioridad 1")
        self.get_logger().info(f"Deadman   -> {self.deadman_topic}")
        self.get_logger().info(f"Auth      -> {self.auth_topic}")
        self.get_logger().info(f"Salida    -> {self.output_topic}")

    def normalize_cmd(self, cmd):
        if not isinstance(cmd, dict):
            return {}

        action = str(cmd.get("action", "")).lower().strip()

        clean_cmd = {}

        if action:
            clean_cmd["action"] = action

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
            clean_cmd["speed_hz"] = speed
            clean_cmd["hz"] = speed

        return clean_cmd

    def publish_output(self, cmd, reason=""):
        out = String()
        out.data = json.dumps(cmd)
        self.cmd_pub.publish(out)

        self.get_logger().info(f"[SALIDA] reason={reason} -> {out.data}")

    def deadman_callback(self, msg: String):
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warn(f"Deadman JSON inválido: {msg.data}")
            return

        self.deadman_pressed = bool(data.get("pressed", False))
        self.last_deadman_time = time.time()

        if self.deadman_pressed:
            self.deadman_stop_sent = False

        self.get_logger().debug(
            f"[DEADMAN] pressed={self.deadman_pressed}"
        )

    def auth_callback(self, msg: String):
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warn(f"Auth JSON inválido: {msg.data}")
            return

        self.face_role = str(data.get("role", "none")).lower().strip()
        self.face_name = str(data.get("name", "none"))
        self.face_detected = bool(data.get("face_detected", False))
        self.face_confidence = float(data.get("confidence", 0.0) or 0.0)
        self.last_auth_time = time.time()

        self.get_logger().info(
            f"[AUTH RX] role={self.face_role}, name={self.face_name}, "
            f"detected={self.face_detected}, conf={self.face_confidence:.2f}"
        )

    def deadman_is_active(self):
        if not self.require_deadman:
            return True

        if self.last_deadman_time <= 0:
            return False

        elapsed = time.time() - self.last_deadman_time

        if elapsed > self.deadman_timeout_sec:
            return False

        return self.deadman_pressed

    def auth_is_fresh(self):
        if self.last_auth_time <= 0:
            return False

        return (time.time() - self.last_auth_time) <= self.auth_timeout_sec

    def current_role(self):
        if not self.auth_is_fresh():
            return "none"

        return self.face_role

    def auth_allows(self, source, cmd):
        action = cmd.get("action", "")
        role = self.current_role()

        if action in ("stop", "emergency_stop"):
            return True, f"{action} siempre permitido"

        if source == "gui":
            return True, "GUI local permitida con deadman"

        if role == "jefe":
            return True, "jefe autorizado"

        if role == "trabajador":
            return False, "trabajador solo puede detener"

        if role in ("otro", "unknown"):
            return False, f"usuario no autorizado: {role}"

        if role == "none":
            return True, "sin cara detectada: modo normal"

        return False, f"rol desconocido: {role}"

    def should_accept_priority(self, source, cmd):
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

        return False, f"bloqueado por prioridad de {self.last_accepted_source}"

    def safety_watchdog(self):
        if self.deadman_is_active():
            self.deadman_stop_sent = False
            return

        if self.deadman_stop_sent:
            return

        self.publish_output(
            {"action": "stop"},
            reason="deadman inactivo, stop automático",
        )

        self.deadman_stop_sent = True

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

        action = cmd.get("action", "")

        if not self.deadman_is_active() and action not in ("stop", "emergency_stop"):
            self.get_logger().warn(
                f"[RECHAZADO] source={source} reason=deadman inactivo cmd={cmd}"
            )

            self.publish_output(
                {"action": "stop"},
                reason="comando rechazado por deadman inactivo",
            )

            self.deadman_stop_sent = True
            return

        auth_ok, auth_reason = self.auth_allows(source, cmd)

        if not auth_ok:
            self.get_logger().warn(
                f"[RECHAZADO] source={source} reason={auth_reason} cmd={cmd}"
            )
            return

        priority_ok, priority_reason = self.should_accept_priority(source, cmd)

        if not priority_ok:
            self.get_logger().warn(
                f"[RECHAZADO] source={source} reason={priority_reason} cmd={cmd}"
            )
            return

        self.publish_output(
            cmd,
            reason=f"aceptado source={source}, auth={auth_reason}, priority={priority_reason}",
        )

        self.last_accepted_source = source
        self.last_accepted_time = time.time()


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
