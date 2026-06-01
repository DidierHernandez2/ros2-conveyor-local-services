#!/usr/bin/env python3

import cv2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage


class WebcamNode(Node):
    def __init__(self):
        super().__init__("webcam_node")

        self.declare_parameter("camera_id", 0)
        self.declare_parameter("fps", 20.0)
        self.declare_parameter("jpeg_quality", 80)

        camera_id = int(self.get_parameter("camera_id").value)
        fps = float(self.get_parameter("fps").value)
        self.jpeg_quality = int(self.get_parameter("jpeg_quality").value)

        self.cap = cv2.VideoCapture(camera_id)

        if not self.cap.isOpened():
            raise RuntimeError(f"No se pudo abrir la cámara {camera_id}")

        self.pub = self.create_publisher(
            CompressedImage,
            "/camera/image/compressed",
            10,
        )

        self.timer = self.create_timer(1.0 / fps, self.publish_frame)

        self.get_logger().info(f"Cámara iniciada en ID {camera_id}")

    def publish_frame(self):
        ret, frame = self.cap.read()

        if not ret:
            self.get_logger().warn("No se pudo leer frame")
            return

        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
        ok, encoded = cv2.imencode(".jpg", frame, encode_params)

        if not ok:
            self.get_logger().warn("No se pudo comprimir imagen")
            return

        msg = CompressedImage()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "webcam"
        msg.format = "jpeg"
        msg.data = encoded.tobytes()

        self.pub.publish(msg)

    def destroy_node(self):
        self.cap.release()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = WebcamNode()

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
