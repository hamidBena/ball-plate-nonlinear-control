import sys
import serial
import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters as pg_exporters
from pyqtgraph.Qt import QtWidgets, QtCore, QtGui
from datetime import datetime
import matplotlib.pyplot as plt
import os
from typing import cast

# ---------- CONFIG ----------
PORT = 'COM5'        # change to your serial port
BAUD = 115200
N = 300              # rolling window size
LOG_TO_FILE = True
SAVE_ALL_ON_EXIT = True
OUTPUT_DIR = "outputs"
SUMMARY_DPI = 150
AUTO_RECONNECT = True
RECONNECT_INTERVAL_MS = 1000

# ---------- SERIAL ----------
try:
    ser = serial.Serial(PORT, BAUD, timeout=0)
except serial.SerialException as exc:
    print(f"Failed to open serial port {PORT}: {exc}")
    sys.exit(1)

# ---------- FILE NAMES ----------
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
os.makedirs(OUTPUT_DIR, exist_ok=True)
csv_file = os.path.join(OUTPUT_DIR, f"data_log_{timestamp}.csv")
summary_file = os.path.join(OUTPUT_DIR, f"summary_{timestamp}.png")

# ---------- QT APPLICATION ----------
app = QtWidgets.QApplication(sys.argv)
pg.setConfigOptions(antialias=True)

paused = False
reconnecting = False

class PlotWindow(pg.GraphicsLayoutWidget):
    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if SAVE_ALL_ON_EXIT:
            save_all()
        shutdown()
        event.accept()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        global paused
        if event.key() == QtCore.Qt.Key.Key_Space:
            paused = not paused
            if paused:
                timer.stop()
            else:
                timer.start(5)
        elif event.key() == QtCore.Qt.Key.Key_S:
            save_all()
        else:
            super().keyPressEvent(event)

win = PlotWindow(title="ESP32 Rolling Signals + Stats")
win.resize(1100, 600)

# ---------- MAIN PLOT ----------
plot = win.addPlot(title=f"Last {N} Samples")
plot.showGrid(x=True, y=True)
plot.addLegend(offset=(10, 10))
plot.setLabel('bottom', 'Sample')
plot.setLabel('left', 'Value')

curve_x = plot.plot(pen=pg.mkPen((255, 80, 80), width=2), name="X")
curve_y = plot.plot(pen=pg.mkPen((80, 255, 80), width=2), name="Y")
curve_p = plot.plot(pen=pg.mkPen((80, 160, 255), width=2), name="Pressure")

# ---------- STAT TEXT ----------
win.nextRow()
stats_text = pg.TextItem(anchor=(0, 0))
plot.addItem(stats_text)

# ---------- BUFFERS ----------
x_buf = np.zeros(N)
y_buf = np.zeros(N)
p_buf = np.zeros(N)
idx = 0
filled = False

x_hist = []
y_hist = []
p_hist = []

# ---------- OPEN CSV ----------
if LOG_TO_FILE:
    csv_f = open(csv_file, "w")
    csv_f.write("x,y,pressure\n")

def safe_stats(arr: np.ndarray):
    if arr.size == 0:
        return None
    return {
        "min": float(arr.min()),
        "max": float(arr.max()),
        "mean": float(arr.mean()),
        "std": float(arr.std()),
    }

# ---------- UPDATE FUNCTION ----------
def update():
    global idx, filled

    updated = False
    try:
        while ser.in_waiting:
            try:
                line = ser.readline().decode().strip()
                if not line:
                    return
                x, y, p = line.split(',')
                x, y, p = float(x), float(y), float(p)

                # Rolling buffer
                x_buf[idx] = x
                y_buf[idx] = y
                p_buf[idx] = p
                idx = (idx + 1) % N
                if idx == 0:
                    filled = True

                # Full history
                x_hist.append(x)
                y_hist.append(y)
                p_hist.append(p)

                # Log to CSV
                if LOG_TO_FILE:
                    csv_f.write(f"{x},{y},{p}\n")
                    if len(x_hist) % 50 == 0:
                        csv_f.flush()

                updated = True
            except ValueError:
                pass
    except serial.SerialException as exc:
        handle_serial_error(exc)
        return

    if not updated:
        return

    # Update plot
    if filled:
        order = np.arange(idx, idx + N) % N
        curve_x.setData(x_buf[order])
        curve_y.setData(y_buf[order])
        curve_p.setData(p_buf[order])
    else:
        curve_x.setData(x_buf[:idx])
        curve_y.setData(y_buf[:idx])
        curve_p.setData(p_buf[:idx])

    # Update stats text
    x_arr = np.array(x_hist)
    y_arr = np.array(y_hist)
    p_arr = np.array(p_hist)

    x_stats = safe_stats(x_arr)
    y_stats = safe_stats(y_arr)
    p_stats = safe_stats(p_arr)

    if x_stats and y_stats and p_stats:
        status = "PAUSED" if paused else "RUNNING"
        stats_text.setText(
            f"""
Status: {status}
X: min={x_stats['min']:.4f}  max={x_stats['max']:.4f}  mean={x_stats['mean']:.4f}  std={x_stats['std']:.4f}
Y: min={y_stats['min']:.4f}  max={y_stats['max']:.4f}  mean={y_stats['mean']:.4f}  std={y_stats['std']:.4f}
P: min={p_stats['min']:.2f}  max={p_stats['max']:.2f}  mean={p_stats['mean']:.2f}  std={p_stats['std']:.2f}
Samples: {len(x_arr)}
""".strip()
        )
    else:
        stats_text.setText("Waiting for data...\nPress SPACE to pause/resume, S to save summary.")

# ---------- TIMER ----------
timer = QtCore.QTimer()
timer.timeout.connect(update)
timer.start(5)

def handle_serial_error(exc: Exception) -> None:
    global reconnecting, paused
    paused = True
    timer.stop()
    stats_text.setText(
        f"Serial disconnected.\n{exc}\nAttempting reconnect..."
    )
    if AUTO_RECONNECT and not reconnecting:
        reconnecting = True
        QtCore.QTimer.singleShot(RECONNECT_INTERVAL_MS, try_reconnect)

def try_reconnect() -> None:
    global ser, reconnecting, paused
    try:
        ser.close()
    except Exception:
        pass

    try:
        ser = serial.Serial(PORT, BAUD, timeout=0)
        reconnecting = False
        paused = False
        timer.start(5)
        stats_text.setText("Reconnected. Receiving data...")
    except serial.SerialException as exc:
        stats_text.setText(f"Reconnect failed: {exc}\nRetrying...")
        QtCore.QTimer.singleShot(RECONNECT_INTERVAL_MS, try_reconnect)

# ---------- SAVE ALL FUNCTION ----------
def save_all():
    if len(x_hist) == 0:
        print("No data collected yet; nothing to save.")
        return

    plt.style.use("seaborn-v0_8")
    x_arr = np.array(x_hist)
    y_arr = np.array(y_hist)
    p_arr = np.array(p_hist)

    x_stats = safe_stats(x_arr)
    y_stats = safe_stats(y_arr)
    p_stats = safe_stats(p_arr)
    if not (x_stats and y_stats and p_stats):
        print("No data collected yet; nothing to save.")
        return

    x_stats = cast(dict[str, float], x_stats)
    y_stats = cast(dict[str, float], y_stats)
    p_stats = cast(dict[str, float], p_stats)

    fig = plt.figure(figsize=(13, 9), dpi=SUMMARY_DPI)
    gs = fig.add_gridspec(4, 2, height_ratios=[2.2, 1, 1, 1], width_ratios=[3, 1.2])

    ax_main = fig.add_subplot(gs[0, :])
    ax_hist_x = fig.add_subplot(gs[1, 0])
    ax_hist_y = fig.add_subplot(gs[2, 0])
    ax_hist_p = fig.add_subplot(gs[3, 0])
    ax_stats = fig.add_subplot(gs[1:, 1])

    t = np.arange(len(x_arr))
    ax_main.plot(t, x_arr, color="#ff5050", lw=1.5, label="X")
    ax_main.plot(t, y_arr, color="#50ff50", lw=1.5, label="Y")
    ax_main.plot(t, p_arr, color="#5090ff", lw=1.5, label="Pressure")
    ax_main.set_title("Full Session Data")
    ax_main.set_xlabel("Sample")
    ax_main.set_ylabel("Value")
    ax_main.grid(True, alpha=0.3)
    ax_main.legend(loc="upper right")

    ax_hist_x.hist(x_arr, bins=50, color="#ff5050", alpha=0.7)
    ax_hist_x.set_title("X Histogram")
    ax_hist_y.hist(y_arr, bins=50, color="#50ff50", alpha=0.7)
    ax_hist_y.set_title("Y Histogram")
    ax_hist_p.hist(p_arr, bins=50, color="#5090ff", alpha=0.7)
    ax_hist_p.set_title("Pressure Histogram")

    for ax in (ax_hist_x, ax_hist_y, ax_hist_p):
        ax.grid(True, alpha=0.3)
        ax.set_ylabel("Count")

    ax_stats.axis("off")
    stats_text_block = (
        f"Session Summary\n"
        f"Port: {PORT}  |  Baud: {BAUD}\n"
        f"Samples: {len(x_arr)}\n\n"
        f"X  min={x_stats['min']:.4f}\n"
        f"   max={x_stats['max']:.4f}\n"
        f"   mean={x_stats['mean']:.4f}\n"
        f"   std={x_stats['std']:.4f}\n\n"
        f"Y  min={y_stats['min']:.4f}\n"
        f"   max={y_stats['max']:.4f}\n"
        f"   mean={y_stats['mean']:.4f}\n"
        f"   std={y_stats['std']:.4f}\n\n"
        f"P  min={p_stats['min']:.2f}\n"
        f"   max={p_stats['max']:.2f}\n"
        f"   mean={p_stats['mean']:.2f}\n"
        f"   std={p_stats['std']:.2f}\n"
    )
    ax_stats.text(0.02, 0.98, stats_text_block, va="top", ha="left", fontsize=10)

    fig.suptitle(f"ESP32 Session Summary - {timestamp}")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(summary_file)
    plt.close(fig)
    print(f"Saved summary image: {summary_file}")

def shutdown():
    if LOG_TO_FILE:
        csv_f.flush()
        csv_f.close()
    ser.close()

# ---------- RUN ----------
win.show()
sys.exit(app.exec_())
