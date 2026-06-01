#!/usr/bin/env python3

import json
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from pymodbus.client import ModbusSerialClient


REG_OP_SIGNAL = 9473
REG_FREQ_CMD = 9474

REG_STATE = 9504
REG_ERR = 9505
REG_FREQ_RD = 9507
REG_FREQ_OUT = 9508
REG_CURRENT = 9511

MIN_HZ = 0.0
MAX_HZ = 60.0


class L510Controller:
    def __init__(self, port: str, slave: int, baudrate: int):
        self.slave = slave
        self.client = ModbusSerialClient(
            port=port,
            baudrate=baudrate,
            parity="N",
            stopbits=1,
            bytesize=8,
            timeout=1.0,
        )

    def connect(self) -> bool:
        return self.client.connect()

    def close(self):
        self.client.close()

    def read_register(self, address: int):
        rr = self.client.read_holding_registers(
            address,
            count=1,
            device_id=self.slave,
        )
        if rr.isError():
            return None
        return rr.registers[0]

    def write_register(self, address: int, value: int) -> bool:
        wr = self.client.write_register(
            address,
            value,
            device_id=self.slave,
        )
        return not wr.isError()

    def hz_to_word(self, hz: float) -> int:
        hz = max(MIN_HZ, min(MAX_HZ, hz))
        return int(round(hz * 100))

    def word_to_hz(self, value):
        if value is None:
            return None
        return value / 100.0

    def set_speed(self, hz: float) -> bool:
        return self.write_register(REG_FREQ_CMD, self.hz_to_word(hz))

    def forward(self) -> bool:
        return self.write_register(REG_OP_SIGNAL, 1)

    def reverse(self) -> bool:
        return self.write_register(REG_OP_SIGNAL, 3)

    def stop(self) -> bool:
        return self.write_register(REG_OP_SIGNAL, 0)

    def controlled_stop(self) -> bool:
        """
        STOP normal mejorado:
        1. Baja referencia de frecuencia a 0 Hz.
        2. Espera un instante.
        3. Manda STOP varias veces.
        """
        ok = True

        ok = self.set_speed(0.0) and ok
        time.sleep(0.10)

        for _ in range(3):
            ok = self.stop() and ok
            time.sleep(0.05)

        return ok

    def emergency_stop(self) -> bool:
        """
        Paro rápido por software.
        No sustituye un paro físico de emergencia.
        """
        ok = True

        ok = self.set_speed(0.0) and ok
        time.sleep(0.05)

        for _ in range(5):
            ok = self.stop() and ok
            time.sleep(0.03)

        return ok

    def get_telemetry(self) -> dict:
        state = self.read_register(REG_STATE)
        error = self.read_register(REG_ERR)
        freq_cmd = self.read_register(REG_FREQ_RD)
        freq_out = self.read_register(REG_FREQ_OUT)
        current = self.read_register(REG_CURRENT)

        return {
            "state": state,
            "error": error,
            "freq_cmd_hz": self.word_to_hz(freq_cmd),
            "freq_out_hz": self.word_to_hz(freq_out),
            "current_raw": current,
            "timestamp": time.time(),
        }


class L510Node(Node):
    def __init__(self):
        super().__init__("l510_node")

        self.declare_parameter("port", "/dev/l510_rs485")
        self.declare_parameter("slave", 1)
        self.declare_parameter("baudrate", 9600)
        self.declare_parameter("initial_speed", 10.0)
        self.declare_parameter("telemetry_period", 0.5)
        self.declare_parameter("cmd_topic", "/conveyor/cmd")
        self.declare_parameter("telemetry_topic", "/conveyor/telemetry")

        port = self.get_parameter("port").value
        slave = int(self.get_parameter("slave").value)
        baudrate = int(self.get_parameter("baudrate").value)
        initial_speed = float(self.get_parameter("initial_speed").value)
        telemetry_period = float(self.get_parameter("telemetry_period").value)
        cmd_topic = self.get_parameter("cmd_topic").value
        telemetry_topic = self.get_parameter("telemetry_topic").value

        self.current_speed_hz = max(MIN_HZ, min(MAX_HZ, initial_speed))
        self.last_direction = None

        self.ctrl = L510Controller(port, slave, baudrate)

        if not self.ctrl.connect():
            raise RuntimeError(f"No se pudo conectar al L510 en {port}")

        self.get_logger().info(f"L510 conectado en {port}, slave={slave}")

        self.cmd_sub = self.create_subscription(
            String,
            cmd_topic,
            self.cmd_callback,
            10,
        )

        self.telemetry_pub = self.create_publisher(
            String,
            telemetry_topic,
            10,
        )

        self.get_logger().info(f"Suscrito a comandos: {cmd_topic}")
        self.get_logger().info(f"Publicando telemetría: {telemetry_topic}")

        self.ctrl.controlled_stop()
        time.sleep(0.3)
        self.ctrl.set_speed(self.current_speed_hz)

        self.timer = self.create_timer(telemetry_period, self.publish_telemetry)

    def get_speed_from_cmd(self, cmd: dict, default=None):
        for key in ("speed_hz", "hz", "speed", "frequency", "freq_hz"):
            value = cmd.get(key, None)

            if value is not None:
                try:
                    hz = float(value)
                    return max(MIN_HZ, min(MAX_HZ, hz))
                except Exception:
                    return default

        return default

    def publish_telemetry(self):
        try:
            data = self.ctrl.get_telemetry()
        except Exception as e:
            self.get_logger().warn(f"Error leyendo telemetría: {e}")
            data = {
                "state": None,
                "error": None,
                "freq_cmd_hz": None,
                "freq_out_hz": None,
                "current_raw": None,
                "timestamp": time.time(),
            }

        msg = String()
        msg.data = json.dumps(data)
        self.telemetry_pub.publish(msg)

    def cmd_callback(self, msg: String):
        try:
            cmd = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().error(f"Comando inválido, no es JSON: {msg.data}")
            return

        action = str(cmd.get("action", "")).lower().strip()
        requested_speed = self.get_speed_from_cmd(cmd, default=None)

        self.get_logger().info(
            f"[CMD RX] action={action}, requested_speed={requested_speed}, raw={msg.data}"
        )

        if action == "set_speed":
            if requested_speed is None:
                self.get_logger().warn("set_speed sin hz/speed_hz")
                return

            self.current_speed_hz = requested_speed

            if self.ctrl.set_speed(self.current_speed_hz):
                self.get_logger().info(f"Velocidad enviada: {self.current_speed_hz:.2f} Hz")
            else:
                self.get_logger().error("Falló set_speed")

        elif action == "forward":
            if requested_speed is not None:
                self.current_speed_hz = requested_speed
                if not self.ctrl.set_speed(self.current_speed_hz):
                    self.get_logger().error("Falló set_speed antes de forward")
                    return
                time.sleep(0.05)

            if self.ctrl.forward():
                self.last_direction = "forward"
                self.get_logger().info(
                    f"FORWARD enviado a {self.current_speed_hz:.2f} Hz"
                )
            else:
                self.get_logger().error("Falló forward")

        elif action == "reverse":
            if requested_speed is not None:
                self.current_speed_hz = requested_speed
                if not self.ctrl.set_speed(self.current_speed_hz):
                    self.get_logger().error("Falló set_speed antes de reverse")
                    return
                time.sleep(0.05)

            if self.ctrl.reverse():
                self.last_direction = "reverse"
                self.get_logger().info(
                    f"REVERSE enviado a {self.current_speed_hz:.2f} Hz"
                )
            else:
                self.get_logger().error("Falló reverse")

        elif action == "stop":
            if self.ctrl.controlled_stop():
                self.last_direction = None
                self.current_speed_hz = 0.0
                self.get_logger().info("STOP enviado: velocidad 0.0 Hz + STOP")
            else:
                self.get_logger().error("Falló stop controlado")

        elif action == "emergency_stop":
            self.get_logger().warn("EMERGENCY STOP solicitado")

            if self.ctrl.emergency_stop():
                self.last_direction = None
                self.current_speed_hz = 0.0
                self.get_logger().warn("EMERGENCY STOP ejecutado: 0 Hz + STOP")
            else:
                self.get_logger().error("Falló emergency_stop")

        elif action == "reset_fault":
            self.get_logger().warn("reset_fault solicitado, aún no implementado")

        else:
            self.get_logger().warn(f"Acción desconocida: {action}")

        self.publish_telemetry()

    def destroy_node(self):
        try:
            self.ctrl.emergency_stop()
            self.ctrl.close()
        except Exception:
            pass

        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = L510Node()

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
