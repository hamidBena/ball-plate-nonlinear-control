from __future__ import annotations

import queue
import re
import threading
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk

import serial


# python imu_visualizer.py COM5 // to run


PORT = "COM5"
BAUD = 115200


TELEMETRY_PATTERN = re.compile(
    r"Setpoints:\s*\(([-+0-9.eE]+),\s*([-+0-9.eE]+)\)\s*\|\s*Measurements:\s*\(([-+0-9.eE]+),\s*([-+0-9.eE]+)\)\s*\|\s*PidX:\s*([-+0-9.eE]+)\s*\|\s*PidY:\s*([-+0-9.eE]+)",
    re.IGNORECASE,
)


@dataclass
class AxisTune:
    kp: tk.DoubleVar
    ki: tk.DoubleVar
    kd: tk.DoubleVar
    setpoint: tk.DoubleVar


class SerialLink:
    def __init__(self, port: str, baud: int) -> None:
        self.port = port
        self.baud = baud
        self.ser: serial.Serial | None = None
        self.reader_thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.incoming: queue.Queue[str] = queue.Queue()

    def connect(self) -> None:
        if self.ser and self.ser.is_open:
            return
        self.ser = serial.Serial(self.port, self.baud, timeout=0.1)
        self.stop_event.clear()
        self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader_thread.start()

    def close(self) -> None:
        self.stop_event.set()
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except serial.SerialException:
                pass

    def send(self, text: str) -> None:
        if not self.ser or not self.ser.is_open:
            raise RuntimeError("serial port is not open")
        self.ser.write((text.rstrip() + "\n").encode("utf-8"))

    def _reader_loop(self) -> None:
        assert self.ser is not None
        while not self.stop_event.is_set() and self.ser and self.ser.is_open:
            try:
                line = self.ser.readline().decode("utf-8", errors="ignore").strip()
            except serial.SerialException as exc:
                self.incoming.put(f"[serial error] {exc}")
                break
            if line:
                self.incoming.put(line)


class PidTunerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("PID Tuner")
        self.root.geometry("920x620")
        self.root.minsize(860, 560)

        self.serial = SerialLink(PORT, BAUD)

        self.axis_x = AxisTune(
            kp=tk.DoubleVar(value=0.1),
            ki=tk.DoubleVar(value=0.0),
            kd=tk.DoubleVar(value=0.0),
            setpoint=tk.DoubleVar(value=0.0),
        )
        self.axis_y = AxisTune(
            kp=tk.DoubleVar(value=0.1),
            ki=tk.DoubleVar(value=0.0),
            kd=tk.DoubleVar(value=0.0),
            setpoint=tk.DoubleVar(value=0.0),
        )

        self.status_var = tk.StringVar(value=f"Disconnected from {PORT}")
        self.last_values_var = tk.StringVar(value="Waiting for telemetry...")

        self._build_ui()
        self._poll_serial_queue()

    def _build_ui(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        container = ttk.Frame(self, padding=16)
        container.pack(fill="both", expand=True)

        header = ttk.Frame(container)
        header.pack(fill="x")

        ttk.Label(header, text="PID Tuner", font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Label(header, textvariable=self.status_var).pack(side="right")

        connection = ttk.Frame(container)
        connection.pack(fill="x", pady=(12, 14))

        ttk.Label(connection, text="Port").grid(row=0, column=0, sticky="w")
        ttk.Entry(connection, width=12, state="readonly", textvariable=tk.StringVar(value=PORT)).grid(row=1, column=0, padx=(0, 10), sticky="w")
        ttk.Label(connection, text="Baud").grid(row=0, column=1, sticky="w")
        ttk.Entry(connection, width=12, state="readonly", textvariable=tk.StringVar(value=str(BAUD))).grid(row=1, column=1, padx=(0, 10), sticky="w")
        ttk.Button(connection, text="Connect", command=self.connect).grid(row=1, column=2, padx=(0, 8))
        ttk.Button(connection, text="Disconnect", command=self.disconnect).grid(row=1, column=3)
        ttk.Label(connection, textvariable=self.last_values_var).grid(row=2, column=0, columnspan=4, sticky="w", pady=(10, 0))

        axes = ttk.Frame(container)
        axes.pack(fill="x", pady=(0, 14))
        axes.columnconfigure(0, weight=1)
        axes.columnconfigure(1, weight=1)

        self._build_axis_panel(axes, 0, "Axis X", self.axis_x)
        self._build_axis_panel(axes, 1, "Axis Y", self.axis_y)

        actions = ttk.Frame(container)
        actions.pack(fill="x", pady=(0, 12))
        ttk.Button(actions, text="Send X", command=lambda: self.send_axis("PIDX", self.axis_x)).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Send Y", command=lambda: self.send_axis("PIDY", self.axis_y)).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Send Both", command=self.send_both).pack(side="left")

        log_frame = ttk.LabelFrame(container, text="Serial log", padding=10)
        log_frame.pack(fill="both", expand=True)

        self.log = tk.Text(log_frame, height=14, wrap="none")
        self.log.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scrollbar.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scrollbar.set)

    def _build_axis_panel(self, parent: ttk.Frame, column: int, title: str, axis: AxisTune) -> None:
        frame = ttk.LabelFrame(parent, text=title, padding=12)
        frame.grid(row=0, column=column, padx=(0, 12) if column == 0 else (0, 0), sticky="nsew")

        for row, (label, variable, minimum, maximum) in enumerate(
            [
                ("Kp", axis.kp, 0.0, 10.0),
                ("Ki", axis.ki, 0.0, 5.0),
                ("Kd", axis.kd, 0.0, 50.0),
                ("Setpoint", axis.setpoint, -180.0, 180.0),
            ]
        ):
            ttk.Label(frame, text=label).grid(row=row * 2, column=0, sticky="w")
            ttk.Scale(frame, from_=minimum, to=maximum, variable=variable, orient="horizontal").grid(
                row=row * 2 + 1, column=0, sticky="ew", pady=(0, 8)
            )
            value = ttk.Label(frame, textvariable=tk.StringVar(value=""))
            value.grid(row=row * 2, column=1, padx=(10, 0), sticky="e")

            def update_value(lbl: ttk.Label, var: tk.DoubleVar) -> None:
                lbl.configure(text=f"{var.get():.3f}")

            update_value(value, variable)
            variable.trace_add("write", lambda *_args, lbl=value, var=variable: update_value(lbl, var))

        frame.columnconfigure(0, weight=1)

    def connect(self) -> None:
        try:
            self.serial.connect()
            self.status_var.set(f"Connected to {PORT}")
            self.log_line(f"[connected] {PORT} @ {BAUD}")
        except serial.SerialException as exc:
            self.status_var.set(f"Failed to connect: {exc}")
            self.log_line(f"[error] {exc}")

    def disconnect(self) -> None:
        self.serial.close()
        self.status_var.set(f"Disconnected from {PORT}")
        self.log_line("[disconnected]")

    def send_axis(self, axis_name: str, axis: AxisTune) -> None:
        command = (
            f"SET {axis_name} KP={axis.kp.get():.4f} KI={axis.ki.get():.4f} "
            f"KD={axis.kd.get():.4f} SP={axis.setpoint.get():.4f}"
        )
        try:
            self.serial.send(command)
            self.log_line(f"> {command}")
        except Exception as exc:
            self.log_line(f"[send failed] {exc}")

    def send_both(self) -> None:
        self.send_axis("PIDX", self.axis_x)
        self.send_axis("PIDY", self.axis_y)

    def _poll_serial_queue(self) -> None:
        try:
            while True:
                line = self.serial.incoming.get_nowait()
                self.log_line(line)
                self._update_from_telemetry(line)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_serial_queue)

    def _update_from_telemetry(self, line: str) -> None:
        match = TELEMETRY_PATTERN.search(line)
        if not match:
            return
        set_x, set_y, meas_x, meas_y, pid_x, pid_y = match.groups()
        self.last_values_var.set(
            f"SP=({float(set_x):.2f}, {float(set_y):.2f})  MEAS=({float(meas_x):.2f}, {float(meas_y):.2f})  OUT=({float(pid_x):.2f}, {float(pid_y):.2f})"
        )

    def log_line(self, text: str) -> None:
        self.log.insert("end", text + "\n")
        self.log.see("end")


def main() -> None:
    root = tk.Tk()
    app = PidTunerApp(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.disconnect(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()