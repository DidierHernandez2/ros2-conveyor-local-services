#!/usr/bin/env python3

import json
import signal
import time
import tkinter as tk

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


MIN_HZ = 0.0
MAX_HZ = 60.0


class TouchHMINode(Node):
    def __init__(self):
        super().__init__("touch_hmi_node")

        self.declare_parameter("cmd_topic", "/cmd/gui")
        self.declare_parameter("telemetry_topic", "/conveyor/telemetry")

        self.cmd_topic = self.get_parameter("cmd_topic").value
        self.telemetry_topic = self.get_parameter("telemetry_topic").value

        self.cmd_pub = self.create_publisher(String, self.cmd_topic, 10)

        self.telemetry_sub = self.create_subscription(
            String,
            self.telemetry_topic,
            self.telemetry_callback,
            10,
        )

        self.last_telemetry = {}
        self.first_telemetry_timestamp = None
        self.last_telemetry_timestamp = None

        self.get_logger().info(f"GUI publicando comandos en {self.cmd_topic}")
        self.get_logger().info(f"GUI leyendo telemetría en {self.telemetry_topic}")

    def publish_cmd(self, payload: dict):
        msg = String()
        msg.data = json.dumps(self.normalize_cmd(payload))
        self.cmd_pub.publish(msg)
        self.get_logger().info(f"[GUI CMD] {msg.data}")

    def normalize_cmd(self, payload: dict) -> dict:
        action = str(payload.get("action", "")).lower().strip()
        clean = {"action": action}

        speed = None
        for key in ("speed_hz", "hz", "speed", "frequency", "freq_hz"):
            if key in payload and payload[key] is not None:
                try:
                    speed = float(payload[key])
                    break
                except Exception:
                    pass

        if speed is not None:
            speed = max(MIN_HZ, min(MAX_HZ, speed))
            clean["speed_hz"] = round(speed, 1)
            clean["hz"] = round(speed, 1)

        return clean

    def telemetry_callback(self, msg: String):
        try:
            data = json.loads(msg.data)
            self.last_telemetry = data

            ts = data.get("timestamp", None)
            if ts is not None:
                ts = float(ts)

                if self.first_telemetry_timestamp is None:
                    self.first_telemetry_timestamp = ts

                self.last_telemetry_timestamp = ts

        except Exception:
            pass


class TouchButton(tk.Frame):
    def __init__(self, parent, text, color, active_color, command, font_size=22):
        super().__init__(parent, bg=color, bd=0, highlightthickness=0)

        self.color = color
        self.active_color = active_color
        self.command = command
        self.is_pressed = False

        self.label = tk.Label(
            self,
            text=text,
            font=("Arial", font_size, "bold"),
            bg=color,
            fg="white",
        )
        self.label.pack(fill="both", expand=True)

        self.bind("<ButtonPress-1>", self.on_press)
        self.bind("<ButtonRelease-1>", self.on_release)
        self.label.bind("<ButtonPress-1>", self.on_press)
        self.label.bind("<ButtonRelease-1>", self.on_release)

    def on_press(self, event=None):
        self.is_pressed = True
        self.configure(bg=self.active_color)
        self.label.configure(bg=self.active_color)

    def on_release(self, event=None):
        if self.is_pressed:
            self.is_pressed = False
            self.configure(bg=self.color)
            self.label.configure(bg=self.color)
            self.command()


class ConveyorHerbieGUI:
    def __init__(self, root: tk.Tk, ros_node: TouchHMINode):
        self.root = root
        self.ros_node = ros_node

        self.current_speed_hz = 10.0
        self.last_slider_sent_hz = 10.0
        self.is_stopped = True

        self.root.title("Conveyor Herbie")
        self.root.geometry("1024x600")
        self.root.configure(bg="#eef1f5")
        self.root.attributes("-fullscreen", True)
        self.root.bind("<Escape>", self.exit_gui)
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.protocol("WM_DELETE_WINDOW", self.exit_gui)

        signal.signal(signal.SIGINT, self.handle_sigint)

        self.build_ui()
        self.update_telemetry_ui()

    def handle_sigint(self, sig, frame):
        self.exit_gui()

    def build_ui(self):
        title = tk.Label(
            self.root,
            text="CONVEYOR HERBIE",
            font=("Arial", 36, "bold"),
            bg="#eef1f5",
            fg="#111827",
        )
        title.place(x=0, y=20, width=1024, height=60)

        TouchButton(
            self.root,
            text="ADELANTE",
            color="#16a34a",
            active_color="#14532d",
            command=self.forward,
            font_size=22,
        ).place(x=65, y=125, width=230, height=75)

        TouchButton(
            self.root,
            text="REVERSA",
            color="#2563eb",
            active_color="#1e3a8a",
            command=self.reverse,
            font_size=22,
        ).place(x=65, y=225, width=230, height=75)

        TouchButton(
            self.root,
            text="STOP",
            color="#dc2626",
            active_color="#7f1d1d",
            command=self.stop,
            font_size=30,
        ).place(x=65, y=330, width=230, height=170)

        self.lbl_vel_real = self.metric_card(390, 125, "VELOCIDAD REAL", "0.00 Hz")
        self.lbl_corriente = self.metric_card(390, 205, "CORRIENTE USADA", "0.00")
        self.lbl_estado = self.metric_card(390, 285, "ESTADO DEL SISTEMA", "SIN DATOS")
        self.lbl_timestamp = self.metric_card(390, 365, "TIEMPO DE TELEMETRÍA", "0.0 s")

        self.speed_value = tk.Label(
            self.root,
            text="10.0 Hz",
            font=("Arial", 22, "bold"),
            bg="#eef1f5",
            fg="#2563eb",
        )
        self.speed_value.place(x=565, y=445, width=190, height=40)

        tk.Label(
            self.root,
            text="0",
            font=("Arial", 18, "bold"),
            bg="#eef1f5",
            fg="#111827",
        ).place(x=365, y=500, width=45, height=40)

        tk.Label(
            self.root,
            text="60",
            font=("Arial", 18, "bold"),
            bg="#eef1f5",
            fg="#111827",
        ).place(x=925, y=500, width=55, height=40)

        self.slider = tk.Scale(
            self.root,
            from_=MIN_HZ,
            to=MAX_HZ,
            orient="horizontal",
            resolution=1,
            showvalue=False,
            bg="#eef1f5",
            fg="black",
            troughcolor="#b8c2d1",
            activebackground="#2563eb",
            highlightthickness=0,
            bd=0,
            width=34,
            sliderlength=70,
            length=520,
            command=self.slider_moved,
        )
        self.slider.set(self.current_speed_hz)
        self.slider.place(x=410, y=492, width=515, height=70)

        self.slider.bind("<ButtonRelease-1>", self.slider_released)
#        self.slider.bind("<TouchEnd>", self.slider_released)

    def metric_card(self, x, y, title, value):
        frame = tk.Frame(self.root, bg="#d9dde3")
        frame.place(x=x, y=y, width=560, height=60)

        tk.Label(
            frame,
            text=title,
            font=("Arial", 11, "bold"),
            bg="#d9dde3",
            fg="#4b5563",
            anchor="w",
        ).place(x=18, y=5, width=520, height=20)

        lbl = tk.Label(
            frame,
            text=value,
            font=("Arial", 21, "bold"),
            bg="#d9dde3",
            fg="#111827",
            anchor="w",
        )
        lbl.place(x=18, y=27, width=520, height=28)

        return lbl

    def slider_moved(self, value):
        hz = round(float(value), 1)
        self.current_speed_hz = hz
        self.speed_value.config(text=f"{hz:.1f} Hz")

    def slider_released(self, event=None):
        hz = round(float(self.slider.get()), 1)

        if abs(hz - self.last_slider_sent_hz) < 0.1:
            return

        self.last_slider_sent_hz = hz

        self.ros_node.publish_cmd({
            "action": "set_speed",
            "speed_hz": hz,
            "hz": hz,
        })

    def forward(self):
        hz = round(float(self.slider.get()), 1)
        self.current_speed_hz = hz
        self.is_stopped = False

        self.ros_node.publish_cmd({
            "action": "forward",
            "speed_hz": hz,
            "hz": hz,
        })

    def reverse(self):
        hz = round(float(self.slider.get()), 1)
        self.current_speed_hz = hz
        self.is_stopped = False

        self.ros_node.publish_cmd({
            "action": "reverse",
            "speed_hz": hz,
            "hz": hz,
        })

    def stop(self):
        self.is_stopped = True

        self.ros_node.publish_cmd({
            "action": "stop",
        })

    def interpret_state(self, data: dict) -> str:
        state = data.get("state")
        error = data.get("error")
        freq_out = float(data.get("freq_out_hz", 0.0) or 0.0)

        if error not in (None, 0, 26):
            return f"ERROR {error}"

        if state == 4 or freq_out <= 0.1:
            return "DETENIDA"

        if state in (5, 7) or freq_out > 0.1:
            return "EN MOVIMIENTO"

        return "SIN DATOS"

    def update_telemetry_ui(self):
        data = self.ros_node.last_telemetry

        if data:
            freq_out = float(data.get("freq_out_hz", 0.0) or 0.0)
            current = float(data.get("current_raw", 0.0) or 0.0)

            self.lbl_vel_real.config(text=f"{freq_out:.2f} Hz")
            self.lbl_corriente.config(text=f"{current:.2f}")
            self.lbl_estado.config(text=self.interpret_state(data))

            first_ts = self.ros_node.first_telemetry_timestamp
            last_ts = self.ros_node.last_telemetry_timestamp

            if first_ts is not None and last_ts is not None:
                elapsed = max(0.0, last_ts - first_ts)
                self.lbl_timestamp.config(text=f"{elapsed:.1f} s")
            else:
                self.lbl_timestamp.config(text="0.0 s")
        else:
            self.lbl_vel_real.config(text="0.00 Hz")
            self.lbl_corriente.config(text="0.00")
            self.lbl_estado.config(text="SIN DATOS")
            self.lbl_timestamp.config(text="0.0 s")

        self.root.after(250, self.update_telemetry_ui)

    def exit_gui(self, event=None):
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass

    def toggle_fullscreen(self, event=None):
        current = bool(self.root.attributes("-fullscreen"))
        self.root.attributes("-fullscreen", not current)


def main(args=None):
    rclpy.init(args=args)
    ros_node = TouchHMINode()

    root = tk.Tk()
    ConveyorHerbieGUI(root, ros_node)

    running = {"ok": True}

    def poll_ros():
        if not running["ok"]:
            return

        if not rclpy.ok():
            root.quit()
            root.destroy()
            return

        rclpy.spin_once(ros_node, timeout_sec=0.0)
        root.after(50, poll_ros)

    root.after(50, poll_ros)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        running["ok"] = False

        try:
            root.quit()
            root.destroy()
        except Exception:
            pass

        ros_node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
