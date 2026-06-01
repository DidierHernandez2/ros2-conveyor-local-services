#!/usr/bin/env python3

import json

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Joy
from std_msgs.msg import String


class JoyMapperNode(Node):
    def __init__(self):
        super().__init__("joy_mapper_node")

        self.declare_parameter("axis_speed", 1)
        self.declare_parameter("btn_forward", 0)
        self.declare_parameter("btn_stop", 1)
        self.declare_parameter("btn_reverse", 2)
        self.declare_parameter("btn_emergency", 3)
        self.declare_parameter("deadzone", 0.2)
        self.declare_parameter("min_hz", 0.0)
        self.declare_parameter("max_hz", 60.0)
        self.declare_parameter("step_hz", 1.0)
        self.declare_parameter("initial_hz", 10.0)

        self.axis_speed = int(self.get_parameter("axis_speed").value)
        self.btn_forward = int(self.get_parameter("btn_forward").value)
        self.btn_stop = int(self.get_parameter("btn_stop").value)
        self.btn_reverse = int(self.get_parameter("btn_reverse").value)
        self.btn_emergency = int(self.get_parameter("btn_emergency").value)

        self.deadzone = float(self.get_parameter("deadzone").value)
        self.min_hz = float(self.get_parameter("min_hz").value)
        self.max_hz = float(self.get_parameter("max_hz").value)
        self.step_hz = float(self.get_parameter("step_hz").value)
        self.target_hz = float(self.get_parameter("initial_hz").value)

        self.last_buttons = []

        self.cmd_pub = self.create_publisher(String, "/conveyor/cmd", 10)
        self.joy_sub = self.create_subscription(Joy, "/joy", self.joy_callback, 10)

        self.get_logger().info("Joy mapper listo")

    def publish_cmd(self, payload: dict):
        msg = String()
        msg.data = json.dumps(payload)
        self.cmd_pub.publish(msg)
        self.get_logger().info(f"CMD: {msg.data}")

    def rising_edge(self, buttons, idx: int) -> bool:
        if idx >= len(buttons):
            return False

        old = self.last_buttons[idx] if idx < len(self.last_buttons) else 0
        return buttons[idx] == 1 and old == 0

    def joy_callback(self, msg: Joy):
        if self.rising_edge(msg.buttons, self.btn_forward):
            self.publish_cmd({"action": "forward"})

        if self.rising_edge(msg.buttons, self.btn_stop):
            self.publish_cmd({"action": "stop"})

        if self.rising_edge(msg.buttons, self.btn_reverse):
            self.publish_cmd({"action": "reverse"})

        if self.rising_edge(msg.buttons, self.btn_emergency):
            self.publish_cmd({"action": "emergency_stop"})

        if self.axis_speed < len(msg.axes):
            axis = msg.axes[self.axis_speed]

            if abs(axis) > self.deadzone:
                self.target_hz += axis * self.step_hz
                self.target_hz = max(self.min_hz, min(self.max_hz, self.target_hz))

                self.publish_cmd({
                    "action": "set_speed",
                    "hz": round(self.target_hz, 2),
                })

        self.last_buttons = list(msg.buttons)


def main(args=None):
    rclpy.init(args=args)
    node = JoyMapperNode()

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
