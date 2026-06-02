#!/usr/bin/env python3

import json
import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Joy
from std_msgs.msg import String


class JoyMapperNode(Node):
    def __init__(self):
        super().__init__("joy_mapper_node")

        self.declare_parameter("btn_deadman", 4)
        self.declare_parameter("deadman_topic", "/safety/deadman")
        self.declare_parameter("publish_rate_hz", 10.0)
        self.declare_parameter("joy_timeout_sec", 0.5)

        self.btn_deadman = int(self.get_parameter("btn_deadman").value)
        self.deadman_topic = self.get_parameter("deadman_topic").value
        self.publish_rate_hz = float(self.get_parameter("publish_rate_hz").value)
        self.joy_timeout_sec = float(self.get_parameter("joy_timeout_sec").value)

        self.deadman_pressed = False
        self.last_joy_time = 0.0

        self.deadman_pub = self.create_publisher(
            String,
            self.deadman_topic,
            10,
        )

        self.joy_sub = self.create_subscription(
            Joy,
            "/joy",
            self.joy_callback,
            10,
        )

        period = 1.0 / self.publish_rate_hz
        self.timer = self.create_timer(period, self.publish_deadman)

        self.get_logger().info("Joy deadman listo")
        self.get_logger().info(f"Botón deadman: {self.btn_deadman}")
        self.get_logger().info(f"Publicando en: {self.deadman_topic}")

    def joy_callback(self, msg: Joy):
        self.last_joy_time = time.time()

        if self.btn_deadman < len(msg.buttons):
            self.deadman_pressed = bool(msg.buttons[self.btn_deadman])
        else:
            self.deadman_pressed = False

    def publish_deadman(self):
        now = time.time()

        if now - self.last_joy_time > self.joy_timeout_sec:
            pressed = False
        else:
            pressed = self.deadman_pressed

        payload = {
            "pressed": pressed,
            "timestamp": now,
            "source": "joystick",
            "button": self.btn_deadman,
        }

        msg = String()
        msg.data = json.dumps(payload)
        self.deadman_pub.publish(msg)


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
