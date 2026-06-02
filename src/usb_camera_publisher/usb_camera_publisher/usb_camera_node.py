#!/usr/bin/env python3

import cv2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CompressedImage
from cv_bridge import CvBridge


class UsbCameraNode(Node):
    def __init__(self):
        super().__init__("usb_camera_node")

        # Puede ser:
        # "/dev/yolo_camera"
        # "/dev/video0"
        # o "0"
        self.declare_parameter("camera_device", "/dev/yolo_camera")

        self.declare_parameter("width", 640)
        self.declare_parameter("height", 480)
        self.declare_parameter("fps", 15.0)
        self.declare_parameter("publish_compressed", True)
        self.declare_parameter("jpeg_quality", 60)

        camera_device = str(
            self.get_parameter("camera_device").value
        )

        width = int(self.get_parameter("width").value)
        height = int(self.get_parameter("height").value)
        fps = float(self.get_parameter("fps").value)

        self.publish_compressed = bool(
            self.get_parameter("publish_compressed").value
        )

        self.jpeg_quality = int(
            self.get_parameter("jpeg_quality").value
        )

        self.bridge = CvBridge()

        # Compatibilidad:
        # si viene "0", "1", etc -> int
        # si viene "/dev/yolo_camera" -> string
        try:
            if camera_device.isdigit():
                camera_source = int(camera_device)
            else:
                camera_source = camera_device
        except Exception:
            camera_source = camera_device

        self.get_logger().info(
            f"Intentando abrir cámara: {camera_source}"
        )

        self.cap = cv2.VideoCapture(
            camera_source,
            cv2.CAP_V4L2
        )

        self.cap.set(
            cv2.CAP_PROP_FOURCC,
            cv2.VideoWriter_fourcc(*"MJPG")
        )

        self.cap.set(
            cv2.CAP_PROP_FRAME_WIDTH,
            width
        )

        self.cap.set(
            cv2.CAP_PROP_FRAME_HEIGHT,
            height
        )

        self.cap.set(
            cv2.CAP_PROP_FPS,
            fps
        )

        if not self.cap.isOpened():
            raise RuntimeError(
                f"No se pudo abrir la cámara: {camera_source}"
            )

        self.raw_pub = self.create_publisher(
            Image,
            "/camera/image_raw",
            10,
        )

        self.compressed_pub = self.create_publisher(
            CompressedImage,
            "/camera/image/compressed",
            10,
        )

        period = 1.0 / fps if fps > 0 else 1.0 / 15.0

        self.timer = self.create_timer(
            period,
            self.publish_frame,
        )

        self.get_logger().info("Cámara USB iniciada")
        self.get_logger().info(
            f"Fuente: {camera_source}"
        )
        self.get_logger().info(
            "Publicando /camera/image_raw"
        )
        self.get_logger().info(
            "Publicando /camera/image/compressed"
        )
        self.get_logger().info(
            f"Config: {width}x{height} @ {fps} FPS, JPEG quality={self.jpeg_quality}"
        )

    def publish_frame(self):
        ret, frame = self.cap.read()

        if not ret:
            self.get_logger().warn(
                "No se pudo leer frame de la cámara"
            )
            return

        stamp = self.get_clock().now().to_msg()

        raw_msg = self.bridge.cv2_to_imgmsg(
            frame,
            encoding="bgr8"
        )

        raw_msg.header.stamp = stamp
        raw_msg.header.frame_id = "usb_camera"

        self.raw_pub.publish(raw_msg)

        if self.publish_compressed:
            ok, encoded = cv2.imencode(
                ".jpg",
                frame,
                [
                    int(cv2.IMWRITE_JPEG_QUALITY),
                    self.jpeg_quality,
                ],
            )

            if ok:
                compressed_msg = CompressedImage()

                compressed_msg.header.stamp = stamp
                compressed_msg.header.frame_id = "usb_camera"
                compressed_msg.format = "jpeg"
                compressed_msg.data = encoded.tobytes()

                self.compressed_pub.publish(
                    compressed_msg
                )

    def destroy_node(self):
        try:
            self.cap.release()
        except Exception:
            pass

        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)

    node = UsbCameraNode()

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
