#!/usr/bin/env python3
"""
PID 2D Position Visualizer
Reads lines like:
  Setpoints: (10.00, -5.00) | Measurements: (8.50, -4.20) | PidX: 1.23 | PidY: -0.45

Requirements:
    pip install pyserial matplotlib

Usage:
    python PID.py              # auto-detect port
    python PID.py COM5         # Windows
"""

import sys
import re
import threading
import collections
import time
import serial
import serial.tools.list_ports
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.gridspec import GridSpec

# ── Config ────────────────────────────────────────────────────────────────────
BAUD_RATE   = 115200
WINDOW_SIZE = 500          # number of samples for time-series plots
TRAIL_SIZE  = 900          # number of points shown in the XY trails
PORT        = sys.argv[1] if len(sys.argv) > 1 else None

XY_XLIM = (-150, 150)
XY_YLIM = (-120, 120)

FILTER_ALPHA = 0.2  # exponential filter smoothing factor (0..1, lower = smoother)

# ── Data store ────────────────────────────────────────────────────────────────
N = WINDOW_SIZE
t_idx       = collections.deque(maxlen=N)
sp_x        = collections.deque(maxlen=N)
sp_y        = collections.deque(maxlen=N)
meas_x      = collections.deque(maxlen=N)
meas_y      = collections.deque(maxlen=N)
err_x       = collections.deque(maxlen=N)
err_y       = collections.deque(maxlen=N)

# Trails for the XY plot (setpoint + filtered measurement)
sp_trail_x   = collections.deque(maxlen=TRAIL_SIZE)
sp_trail_y   = collections.deque(maxlen=TRAIL_SIZE)
meas_trail_x = collections.deque(maxlen=TRAIL_SIZE)
meas_trail_y = collections.deque(maxlen=TRAIL_SIZE)

# Exponential filter state for measurements
filt_mx = None
filt_my = None

latest = {}
lock = threading.Lock()
sample_count = 0

# Parse:  Setpoints: (10.00, -5.00) | Measurements: (8.50, -4.20) | PidX: 1.23 | PidY: -0.45
PATTERN = re.compile(
    r"Setpoints:\s*\(\s*([+-]?\d+\.?\d*)\s*,\s*([+-]?\d+\.?\d*)\s*\)"
    r".*?Measurements:\s*\(\s*([+-]?\d+\.?\d*)\s*,\s*([+-]?\d+\.?\d*)\s*\)"
    r".*?ControlX:\s*([+-]?\d+\.?\d*)"
    r".*?ControlY:\s*([+-]?\d+\.?\d*)"
)

def auto_detect_port():
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        return None
    for p in ports:
        desc = (p.description or "").lower()
        if any(k in desc for k in ["usb", "cp210", "ch340", "ftdi", "uart"]):
            return p.device
    return ports[0].device


def serial_reader(port, baud):
    global sample_count, filt_mx, filt_my
    try:
        ser = serial.Serial(port, baud, timeout=1)
        print(f"[✓] Connected to {port} @ {baud} baud")
    except serial.SerialException as e:
        print(f"[✗] Cannot open {port}: {e}")
        sys.exit(1)

    while True:
        try:
            raw = ser.readline().decode("utf-8", errors="ignore").strip()
        except Exception:
            continue
        if not raw:
            continue

        m = PATTERN.search(raw)
        if not m:
            print(f"[?] {raw}")
            continue

        sx, sy = float(m.group(1)), float(m.group(2))
        mx, my = float(m.group(3)), float(m.group(4))
        px, py = float(m.group(5)), float(m.group(6))
        ex, ey = sx - mx, sy - my

        # Exponential filter on measurements for a smoother trail
        if filt_mx is None:
            filt_mx, filt_my = mx, my
        else:
            filt_mx = FILTER_ALPHA * mx + (1 - FILTER_ALPHA) * filt_mx
            filt_my = FILTER_ALPHA * my + (1 - FILTER_ALPHA) * filt_my

        with lock:
            sample_count += 1
            t_idx.append(sample_count)
            sp_x.append(sx); sp_y.append(sy)
            meas_x.append(mx); meas_y.append(my)
            err_x.append(ex); err_y.append(ey)

            sp_trail_x.append(sx); sp_trail_y.append(sy)
            meas_trail_x.append(filt_mx); meas_trail_y.append(filt_my)

            latest.update(dict(sx=sx, sy=sy, mx=mx, my=my,
                                fmx=filt_mx, fmy=filt_my,
                                px=px, py=py, ex=ex, ey=ey))


# ── Plot setup ────────────────────────────────────────────────────────────────
plt.style.use("dark_background")
fig = plt.figure(figsize=(14, 8), facecolor="#0d1117")
fig.canvas.manager.set_window_title("PID Position Visualizer")

gs = GridSpec(2, 2, figure=fig, hspace=0.4, wspace=0.35,
              left=0.06, right=0.97, top=0.90, bottom=0.08,
              width_ratios=[1.4, 1])

ax_xy    = fig.add_subplot(gs[:, 0])   # tall, spans both rows
ax_err   = fig.add_subplot(gs[0, 1])
ax_pidxy = fig.add_subplot(gs[1, 1])
ax_info  = None  # info now overlaid as text box on ax_xy

COLORS = {"x": "#ff4d6d", "y": "#43e97b", "sp": "#f7c873", "meas": "#4fc3f7"}

# --- XY position plot ---
ax_xy.set_facecolor("#161b22")
ax_xy.set_title("Position (Setpoint vs Measurement)", color="#e6edf3", fontsize=10, fontweight="bold", pad=8)
ax_xy.set_xlabel("X", color="#8b949e", fontsize=8)
ax_xy.set_ylabel("Y", color="#8b949e", fontsize=8)
ax_xy.set_xlim(*XY_XLIM)
ax_xy.set_ylim(*XY_YLIM)
ax_xy.set_aspect("equal")
ax_xy.tick_params(colors="#8b949e", labelsize=7)
ax_xy.grid(True, color="#21262d", linewidth=0.6)
ax_xy.axhline(0, color="#30363d", linewidth=0.8)
ax_xy.axvline(0, color="#30363d", linewidth=0.8)
for spine in ax_xy.spines.values():
    spine.set_edgecolor("#30363d")

sp_trail_line,   = ax_xy.plot([], [], "-", color=COLORS["sp"], linewidth=1, alpha=0.4)
meas_trail_line, = ax_xy.plot([], [], "-", color=COLORS["meas"], linewidth=1.5, alpha=0.6)
sp_point,   = ax_xy.plot([], [], "o", color=COLORS["sp"], markersize=10,
                          markeredgecolor="white", markeredgewidth=1, label="Setpoint")
meas_point, = ax_xy.plot([], [], "o", color=COLORS["meas"], markersize=10,
                          markeredgecolor="white", markeredgewidth=1, label="Measurement")
err_line,   = ax_xy.plot([], [], "--", color="#ff4d6d", linewidth=1, alpha=0.7, label="Error")
ax_xy.legend(loc="upper right", fontsize=8, framealpha=0.3,
             labelcolor="white", facecolor="#0d1117")

info_text = ax_xy.text(
    0.02, 0.02, "", transform=ax_xy.transAxes,
    va="bottom", ha="left", fontsize=8, fontfamily="monospace",
    color="#e6edf3", linespacing=1.6,
    bbox=dict(boxstyle="round", facecolor="#161b22", edgecolor="#30363d", alpha=0.8)
)

# --- Error plot ---
ax_err.set_facecolor("#161b22")
ax_err.set_title("Error (Setpoint - Measurement)", color="#e6edf3", fontsize=10, fontweight="bold", pad=6)
ax_err.set_ylabel("Error", color="#8b949e", fontsize=8)
ax_err.tick_params(colors="#8b949e", labelsize=7)
ax_err.grid(True, color="#21262d", linewidth=0.6)
ax_err.set_xlim(0, N)
ax_err.axhline(0, color="#30363d", linewidth=0.8)
for spine in ax_err.spines.values():
    spine.set_edgecolor("#30363d")
ln_errx, = ax_err.plot([], [], color=COLORS["x"], lw=1.2, label="ErrX")
ln_erry, = ax_err.plot([], [], color=COLORS["y"], lw=1.2, label="ErrY")
ax_err.legend(loc="upper left", fontsize=7, framealpha=0.3,
              labelcolor="white", facecolor="#0d1117")

# --- Setpoint vs Measurement over time (X and Y) ---
ax_pidxy.set_facecolor("#161b22")
ax_pidxy.set_title("Setpoint vs Measurement (X & Y)", color="#e6edf3", fontsize=10, fontweight="bold", pad=6)
ax_pidxy.set_ylabel("Value", color="#8b949e", fontsize=8)
ax_pidxy.tick_params(colors="#8b949e", labelsize=7)
ax_pidxy.grid(True, color="#21262d", linewidth=0.6)
ax_pidxy.set_xlim(0, N)
for spine in ax_pidxy.spines.values():
    spine.set_edgecolor("#30363d")
ln_spx, = ax_pidxy.plot([], [], color=COLORS["x"], lw=1.2, ls="--", label="SP X")
ln_mx,  = ax_pidxy.plot([], [], color=COLORS["x"], lw=1.2, label="Meas X")
ln_spy, = ax_pidxy.plot([], [], color=COLORS["y"], lw=1.2, ls="--", label="SP Y")
ln_my,  = ax_pidxy.plot([], [], color=COLORS["y"], lw=1.2, label="Meas Y")
ax_pidxy.legend(loc="upper left", fontsize=6, framealpha=0.3, ncol=2,
                labelcolor="white", facecolor="#0d1117")

fig.suptitle("PID Position Tracking", color="#e6edf3", fontsize=13, fontweight="bold", y=0.96)


def update(_frame):
    with lock:
        _t   = list(t_idx)
        _spx = list(sp_x); _spy = list(sp_y)
        _mx  = list(meas_x); _my = list(meas_y)
        _ex  = list(err_x); _ey = list(err_y)
        _sptx = list(sp_trail_x); _spty = list(sp_trail_y)
        _mtx  = list(meas_trail_x); _mty = list(meas_trail_y)
        _l   = dict(latest)

    if not _l:
        return

    # XY plot: trails + current points
    sp_trail_line.set_data(_sptx, _spty)
    meas_trail_line.set_data(_mtx, _mty)
    sp_point.set_data([_l["sx"]], [_l["sy"]])
    meas_point.set_data([_l["fmx"]], [_l["fmy"]])
    err_line.set_data([_l["sx"], _l["fmx"]], [_l["sy"], _l["fmy"]])

    # x-axis window for time-series plots
    if _t:
        x0, x1 = _t[0], _t[-1]
        if x1 == x0:
            x1 = x0 + 1
    else:
        x0, x1 = 0, N

    for ax_obj in (ax_err, ax_pidxy):
        ax_obj.set_xlim(x0, x1)

    # Error
    ln_errx.set_data(_t, _ex)
    ln_erry.set_data(_t, _ey)
    if _ex or _ey:
        all_v = _ex + _ey
        lo, hi = min(all_v), max(all_v)
        pad = max((hi - lo) * 0.15, 0.5)
        ax_err.set_ylim(lo - pad, hi + pad)

    # SP vs Meas X & Y
    ln_spx.set_data(_t, _spx)
    ln_mx.set_data(_t, _mx)
    ln_spy.set_data(_t, _spy)
    ln_my.set_data(_t, _my)
    if _spx or _mx or _spy or _my:
        all_v = _spx + _mx + _spy + _my
        lo, hi = min(all_v), max(all_v)
        pad = max((hi - lo) * 0.15, 0.5)
        ax_pidxy.set_ylim(lo - pad, hi + pad)

    # Info
    info_text.set_text(
        f"Setpoint : ({_l['sx']:+.2f}, {_l['sy']:+.2f})\n"
        f"Measured : ({_l['mx']:+.2f}, {_l['my']:+.2f})\n"
        f"Filtered : ({_l['fmx']:+.2f}, {_l['fmy']:+.2f})\n"
        f"Error    : ({_l['ex']:+.2f}, {_l['ey']:+.2f})\n"
        f"PID      : ({_l['px']:+.2f}, {_l['py']:+.2f})\n"
        f"Samples  : {sample_count}"
    )

    return (sp_trail_line, meas_trail_line, sp_point, meas_point, err_line,
            ln_errx, ln_erry, ln_spx, ln_mx, ln_spy, ln_my, info_text)


if __name__ == "__main__":
    port = PORT or auto_detect_port()
    if not port:
        print("[✗] No serial port found. Pass the port as an argument.")
        print("    Example: python PID.py /dev/ttyUSB0")
        sys.exit(1)

    print(f"[→] Using port: {port}")
    t = threading.Thread(target=serial_reader, args=(port, BAUD_RATE), daemon=True)
    t.start()

    ani = animation.FuncAnimation(fig, update, interval=50, blit=False, cache_frame_data=False)
    plt.show()