import sys
import serial
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtWidgets, QtCore, QtGui

# ---------- CONFIG ----------
PORT = 'COM5'        # change to your serial port
BAUD = 115200
AUTO_RECONNECT = True
RECONNECT_INTERVAL_MS = 1000

# Auto-ranging settings
AUTO_RANGE_ENABLED = True
RANGE_MARGIN = 0.1  # 10% margin around data range

# Manual range (used if auto-range is disabled)
MANUAL_X_MIN = 0.3
MANUAL_X_MAX = 2.4
MANUAL_Y_MIN = 0.3
MANUAL_Y_MAX = 2.4

# ---------- SERIAL ----------
try:
    ser = serial.Serial(PORT, BAUD, timeout=0)
except serial.SerialException as exc:
    print(f"Failed to open serial port {PORT}: {exc}")
    sys.exit(1)

# ---------- QT APPLICATION ----------
app = QtWidgets.QApplication(sys.argv)
pg.setConfigOptions(antialias=True)

reconnecting = False
paused = False
show_trail = True
show_crosshair = True
show_stats = True

class TouchVisualizer(pg.GraphicsLayoutWidget):
    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        shutdown()
        event.accept()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        global paused, show_trail, show_crosshair, show_stats, AUTO_RANGE_ENABLED
        global trail_x, trail_y, x_history, y_history, p_history
        
        if event.key() == QtCore.Qt.Key.Key_Space:
            paused = not paused
            if paused:
                timer.stop()
            else:
                timer.start(10)
        elif event.key() == QtCore.Qt.Key.Key_T:
            show_trail = not show_trail
            if not show_trail:
                trail_line.setData([], [])
        elif event.key() == QtCore.Qt.Key.Key_C:
            show_crosshair = not show_crosshair
            crosshair_v.setVisible(show_crosshair)
            crosshair_h.setVisible(show_crosshair)
        elif event.key() == QtCore.Qt.Key.Key_S:
            show_stats = not show_stats
            if not show_stats:
                stats_text.setHtml('')
        elif event.key() == QtCore.Qt.Key.Key_R:
            # Reset/clear trail and history
            trail_x.clear()
            trail_y.clear()
            x_history.clear()
            y_history.clear()
            p_history.clear()
        elif event.key() == QtCore.Qt.Key.Key_A:
            AUTO_RANGE_ENABLED = not AUTO_RANGE_ENABLED
        else:
            super().keyPressEvent(event)

win = TouchVisualizer(title="Touch Panel Finger Position Visualizer")
win.resize(1000, 900)

# ---------- MAIN PLOT ----------
plot = win.addPlot(title="<span style='font-size: 16pt; color: #50a0ff;'>Touch Panel Position Tracker</span>")
plot.showGrid(x=True, y=True, alpha=0.3)
plot.setLabel('bottom', '<span style="font-size: 12pt; color: #ff5050;">X Position</span>')
plot.setLabel('left', '<span style="font-size: 12pt; color: #50ff50;">Y Position</span>')
plot.setAspectLocked(True)

# Draw touch panel boundary (will be updated based on range)
boundary = pg.PlotDataItem(
    [],
    [],
    pen=pg.mkPen((100, 100, 100), width=2, style=QtCore.Qt.PenStyle.DashLine)
)
plot.addItem(boundary)

# Center marker
center_marker = pg.ScatterPlotItem(
    size=10,
    pen=pg.mkPen('w', width=1),
    brush=pg.mkBrush(255, 255, 255, 100),
    symbol='+'
)
plot.addItem(center_marker)

# Crosshair for current position
crosshair_v = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('#ffff00', width=1, style=QtCore.Qt.PenStyle.DashLine))
crosshair_h = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('#ffff00', width=1, style=QtCore.Qt.PenStyle.DashLine))
plot.addItem(crosshair_v)
plot.addItem(crosshair_h)

# Current finger position dot - size based on pressure
finger_dot = pg.ScatterPlotItem(
    size=30,
    pen=pg.mkPen('#ffffff', width=2),
    brush=pg.mkBrush(255, 80, 80, 220),
    symbol='o'
)
plot.addItem(finger_dot)

# Heatmap trail with gradient
trail_size = 100
trail_x = []
trail_y = []
trail_line = plot.plot(pen=pg.mkPen((80, 160, 255, 150), width=3))

# ---------- STATS TEXT (bottom) ----------
win.nextRow()
stats_text = pg.TextItem(anchor=(0, 0), color='w')
stats_plot = win.addPlot()
stats_plot.hideAxis('left')
stats_plot.hideAxis('bottom')
stats_plot.setMaximumHeight(120)
stats_plot.addItem(stats_text)
stats_text.setPos(0, 0)

# ---------- DATA ----------
current_x = 1.2
current_y = 1.2
current_p = 0

# History for statistics
x_history = []
y_history = []
p_history = []

# Range tracking
x_min_seen = float('inf')
x_max_seen = float('-inf')
y_min_seen = float('inf')
y_max_seen = float('-inf')

# ---------- UPDATE FUNCTION ----------
def update():
    global current_x, current_y, current_p
    global x_min_seen, x_max_seen, y_min_seen, y_max_seen

    updated = False
    try:
        while ser.in_waiting:
            try:
                line = ser.readline().decode().strip()
                if not line:
                    return
                x, y, p = line.split(',')
                current_x, current_y, current_p = float(x), float(y), float(p)

                # Update history
                x_history.append(current_x)
                y_history.append(current_y)
                p_history.append(current_p)
                
                # Keep history manageable
                max_history = 1000
                if len(x_history) > max_history:
                    x_history.pop(0)
                    y_history.pop(0)
                    p_history.pop(0)

                # Track min/max
                x_min_seen = min(x_min_seen, current_x)
                x_max_seen = max(x_max_seen, current_x)
                y_min_seen = min(y_min_seen, current_y)
                y_max_seen = max(y_max_seen, current_y)

                # Add to trail
                if show_trail:
                    trail_x.append(current_x)
                    trail_y.append(current_y)
                    if len(trail_x) > trail_size:
                        trail_x.pop(0)
                        trail_y.pop(0)

                updated = True
            except ValueError:
                pass
    except serial.SerialException as exc:
        handle_serial_error(exc)
        return

    if not updated:
        return

    # Update range
    if AUTO_RANGE_ENABLED and x_min_seen != float('inf'):
        x_range = x_max_seen - x_min_seen
        y_range = y_max_seen - y_min_seen
        
        x_margin = max(0.1, x_range * RANGE_MARGIN)
        y_margin = max(0.1, y_range * RANGE_MARGIN)
        
        x_min = x_min_seen - x_margin
        x_max = x_max_seen + x_margin
        y_min = y_min_seen - y_margin
        y_max = y_max_seen + y_margin
        
        plot.setXRange(x_min, x_max, padding=0)
        plot.setYRange(y_min, y_max, padding=0)
        
        # Update boundary
        boundary.setData(
            [x_min_seen, x_max_seen, x_max_seen, x_min_seen, x_min_seen],
            [y_min_seen, y_min_seen, y_max_seen, y_max_seen, y_min_seen]
        )
        
        # Update center marker
        center_x = (x_min_seen + x_max_seen) / 2
        center_y = (y_min_seen + y_max_seen) / 2
        center_marker.setData([center_x], [center_y])
    else:
        plot.setXRange(MANUAL_X_MIN, MANUAL_X_MAX, padding=0.05)
        plot.setYRange(MANUAL_Y_MIN, MANUAL_Y_MAX, padding=0.05)
        boundary.setData(
            [MANUAL_X_MIN, MANUAL_X_MAX, MANUAL_X_MAX, MANUAL_X_MIN, MANUAL_X_MIN],
            [MANUAL_Y_MIN, MANUAL_Y_MIN, MANUAL_Y_MAX, MANUAL_Y_MAX, MANUAL_Y_MIN]
        )
        center_marker.setData([(MANUAL_X_MIN + MANUAL_X_MAX) / 2], [(MANUAL_Y_MIN + MANUAL_Y_MAX) / 2])

    # Update crosshair
    if show_crosshair:
        crosshair_v.setPos(current_x)
        crosshair_h.setPos(current_y)

    # Update finger dot - size based on pressure
    dot_size = max(15, min(80, current_p / 5))
    # Color changes with pressure (blue to red)
    pressure_ratio = min(1.0, current_p / 1000.0)
    r = int(255 * pressure_ratio)
    b = int(255 * (1 - pressure_ratio))
    finger_dot.setBrush(pg.mkBrush(r, 80, b, 220))
    finger_dot.setData([current_x], [current_y], size=dot_size)

    # Update trail
    if show_trail and len(trail_x) > 1:
        trail_line.setData(trail_x, trail_y)

    # Update stats text
    if show_stats and len(x_history) > 0:
        x_arr = np.array(x_history)
        y_arr = np.array(y_history)
        p_arr = np.array(p_history)
        
        pressure_bar = "█" * int(current_p / 100) if current_p < 1000 else "█" * 10
        pressure_bar += "░" * max(0, 10 - len(pressure_bar))
        
        status_icon = "⏸" if paused else "▶"
        range_mode = "Auto" if AUTO_RANGE_ENABLED else "Manual"
        
        stats_text.setHtml(
            f'<div style="background-color: rgba(30, 30, 30, 200); padding: 10px; border-radius: 5px;">'
            f'<table style="color: white; font-size: 11pt;">'
            f'<tr><td style="color: #50a0ff; font-weight: bold;">{status_icon} Status:</td><td>{"PAUSED" if paused else "RUNNING"} | Range: {range_mode} | Trail: {"ON" if show_trail else "OFF"} | Crosshair: {"ON" if show_crosshair else "OFF"}</td></tr>'
            f'<tr><td style="color: #ff5050; font-weight: bold;">X:</td><td>{current_x:.3f} (min: {x_arr.min():.3f}, max: {x_arr.max():.3f}, avg: {x_arr.mean():.3f}, σ: {x_arr.std():.3f})</td></tr>'
            f'<tr><td style="color: #50ff50; font-weight: bold;">Y:</td><td>{current_y:.3f} (min: {y_arr.min():.3f}, max: {y_arr.max():.3f}, avg: {y_arr.mean():.3f}, σ: {y_arr.std():.3f})</td></tr>'
            f'<tr><td style="color: #50a0ff; font-weight: bold;">Pressure:</td><td>{current_p:.0f} (min: {p_arr.min():.0f}, max: {p_arr.max():.0f}, avg: {p_arr.mean():.0f}) [{pressure_bar}]</td></tr>'
            f'<tr><td style="color: #aaaaaa;">Samples:</td><td>{len(x_history)} | Hotkeys: [SPACE] Pause [T] Trail [C] Cross [S] Stats [R] Reset [A] AutoRange</td></tr>'
            f'</table>'
            f'</div>'
        )

# ---------- TIMER ----------
timer = QtCore.QTimer()
timer.timeout.connect(update)
timer.start(10)  # Update every 10ms

def handle_serial_error(exc: Exception) -> None:
    global reconnecting
    timer.stop()
    stats_text.setHtml(
        f'<div style="background-color: rgba(200, 50, 50, 200); padding: 10px; border-radius: 5px;">'
        f'<span style="color: white; font-size: 14pt; font-weight: bold;">⚠ Serial Disconnected</span><br>'
        f'<span style="color: white; font-size: 10pt;">{exc}</span><br>'
        f'<span style="color: #ffff00; font-size: 11pt;">🔄 Attempting reconnection...</span>'
        f'</div>'
    )
    if AUTO_RECONNECT and not reconnecting:
        reconnecting = True
        QtCore.QTimer.singleShot(RECONNECT_INTERVAL_MS, try_reconnect)

def try_reconnect() -> None:
    global ser, reconnecting
    try:
        if ser.is_open:
            ser.close()
        ser = serial.Serial(PORT, BAUD, timeout=0)
        reconnecting = False
        timer.start(10)
        print("Reconnected successfully")
    except serial.SerialException as exc:
        print(f"Reconnect failed: {exc}")
        QtCore.QTimer.singleShot(RECONNECT_INTERVAL_MS, try_reconnect)

def shutdown() -> None:
    timer.stop()
    if ser.is_open:
        ser.close()

# ---------- RUN ----------
win.show()
sys.exit(app.exec())
