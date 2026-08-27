import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.widgets import Slider, Button
import re

FILE_PATH = "outputs/kalman_output.txt"

data = {
    "fx": [],  "fy": [],
    "fvx": [], "fvy": [],
    "rx": [],  "ry": [],
    "rvx": [], "rvy": [],
}
last_file_pos = 0
last_filtered = None
last_normal   = None
stats = {"total": 0, "paired": 0, "unpaired_f": 0, "unpaired_n": 0}

RE_FILTERED = re.compile(
    r"Filtered X:\s*([-\d.]+)\s*\|\s*Filtered Y:\s*([-\d.]+)"
    r"\s*\|\|\s*Velocity X:\s*([-\d.]+)\s*\|\s*Velocity Y:\s*([-\d.]+)"
)
RE_NORMAL = re.compile(
    r"normal X:\s*([-\d.]+)\s*\|\s*normal Y:\s*([-\d.]+)"
    r"\s*\|\|\s*Velocity X:\s*([-\d.]+)\s*\|\s*Velocity Y:\s*([-\d.]+)"
)

def try_commit():
    global last_filtered, last_normal
    if last_filtered is not None and last_normal is not None:
        fx, fy, fvx, fvy = last_filtered
        rx, ry, rvx, rvy = last_normal
        data["fx"].append(fx);   data["fy"].append(fy)
        data["fvx"].append(fvx); data["fvy"].append(fvy)
        data["rx"].append(rx);   data["ry"].append(ry)
        data["rvx"].append(rvx); data["rvy"].append(rvy)
        last_filtered = None
        last_normal   = None
        stats["paired"] += 1
        return True
    return False

def read_new_lines():
    global last_file_pos, last_filtered, last_normal
    try:
        f = open(FILE_PATH, "r")
    except FileNotFoundError:
        return False
    f.seek(last_file_pos)
    lines = f.readlines()
    last_file_pos = f.tell()
    f.close()

    added = False
    for line in lines:
        stats["total"] += 1
        mf = RE_FILTERED.search(line)
        mn = RE_NORMAL.search(line)
        if mf:
            if last_filtered is not None:
                stats["unpaired_f"] += 1
            last_filtered = (float(mf.group(1)), float(mf.group(2)),
                             float(mf.group(3)), float(mf.group(4)))
            if try_commit():
                added = True
        elif mn:
            if last_normal is not None:
                stats["unpaired_n"] += 1
            last_normal = (float(mn.group(1)), float(mn.group(2)),
                           float(mn.group(3)), float(mn.group(4)))
            if try_commit():
                added = True
    return added

# ── figure: 2 rows (X on top, Y on bottom), each row overlaps pos+vel ────────
fig, axes = plt.subplots(2, 2, figsize=(15, 8))
fig.patch.set_facecolor("#f5f5f5")
fig.suptitle("Raw vs Kalman — X (top) and Y (bottom), position overlaid with velocity", fontsize=12)

ax_rx, ax_fx = axes[0]   # top row: raw X left, kalman X right
ax_ry, ax_fy = axes[1]   # bottom row: raw Y left, kalman Y right

for ax in axes.flat:
    ax.set_facecolor("#ffffff")
    ax.grid(True, linestyle="--", alpha=0.35, color="#aaa")

ax_rx.set_title("Raw X — position & velocity", fontsize=10)
ax_fx.set_title("Kalman X — position & velocity", fontsize=10)
ax_ry.set_title("Raw Y — position & velocity", fontsize=10)
ax_fy.set_title("Kalman Y — position & velocity", fontsize=10)

for ax in axes.flat:
    ax.set_xlabel("time (s)", fontsize=8)

# each axis gets a twin for the velocity (different y scale)
ax_rx2 = ax_rx.twinx()
ax_fx2 = ax_fx.twinx()
ax_ry2 = ax_ry.twinx()
ax_fy2 = ax_fy.twinx()

for ax in [ax_rx, ax_fx, ax_ry, ax_fy]:
    ax.set_ylabel("position", fontsize=8, color="#378ADD")
    ax.tick_params(axis='y', labelcolor="#378ADD")

for ax in [ax_rx2, ax_fx2, ax_ry2, ax_fy2]:
    ax.set_ylabel("velocity", fontsize=8, color="#D85A30")
    ax.tick_params(axis='y', labelcolor="#D85A30")

BLUE   = "#378ADD"
ORANGE = "#D85A30"

# raw X
ln_rx_pos,  = ax_rx.plot([],  [], color=BLUE,   lw=1.5, label="pos X")
ln_rx_vel,  = ax_rx2.plot([], [], color=ORANGE,  lw=1.0, label="vel X", alpha=0.75)
# kalman X
ln_fx_pos,  = ax_fx.plot([],  [], color=BLUE,   lw=1.5, label="pos X")
ln_fx_vel,  = ax_fx2.plot([], [], color=ORANGE,  lw=1.4, label="vel X")
# raw Y
ln_ry_pos,  = ax_ry.plot([],  [], color="#1D9E75", lw=1.5, label="pos Y")
ln_ry_vel,  = ax_ry2.plot([], [], color="#BA7517",  lw=1.0, label="vel Y", alpha=0.75)
# kalman Y
ln_fy_pos,  = ax_fy.plot([],  [], color="#1D9E75", lw=1.5, label="pos Y")
ln_fy_vel,  = ax_fy2.plot([], [], color="#BA7517",  lw=1.4, label="vel Y")

# legends — combine both axes per plot
for ax, ax2 in [(ax_rx, ax_rx2), (ax_fx, ax_fx2), (ax_ry, ax_ry2), (ax_fy, ax_fy2)]:
    lines  = ax.get_lines()  + ax2.get_lines()
    labels = [l.get_label() for l in lines]
    ax.legend(lines, labels, fontsize=8, loc="upper left")

# ── sliders ───────────────────────────────────────────────────────────────────
plt.subplots_adjust(bottom=0.15, hspace=0.42, wspace=0.35)

def make_slider(left, bottom, label, vmin, vmax, vinit, fmt="%0.4f"):
    ax_s = fig.add_axes([left, bottom, 0.35, 0.022], facecolor="#e8e8e8")
    s = Slider(ax_s, label, vmin, vmax, valinit=vinit, valfmt=fmt, color=BLUE)
    s.label.set_fontsize(8)
    s.valtext.set_fontsize(8)
    return s

sl_dt  = make_slider(0.08, 0.075, "dt (s)",            0.001, 0.5,  0.033, "%0.4f")
sl_win = make_slider(0.55, 0.075, "Window (s)",        1.0,   120,  30.0,  "%0.1f")

ax_btn_all   = fig.add_axes([0.91, 0.068, 0.07, 0.032])
btn_all = Button(ax_btn_all, "Show all", color="#ddd", hovercolor="#bbb")
show_all = [False]

def on_show_all(_):
    show_all[0] = not show_all[0]
    btn_all.label.set_text("Show all ✓" if show_all[0] else "Show all")
    redraw()

btn_all.on_clicked(on_show_all)
sl_dt.on_changed(lambda _: redraw())
sl_win.on_changed(lambda _: redraw())

status  = fig.text(0.01, 0.005, "", fontsize=8, color="#555", family="monospace")
debug_t = fig.text(0.01, 0.975, "", fontsize=7, color="#e07000", family="monospace")

# ── draw ──────────────────────────────────────────────────────────────────────
def redraw():
    n = len(data["fx"])
    if n == 0:
        status.set_text("no data yet — waiting for file...")
        debug_t.set_text(
            f"lines read: {stats['total']}  paired: {stats['paired']}  "
            f"unpaired filtered: {stats['unpaired_f']}  unpaired normal: {stats['unpaired_n']}"
        )
        fig.canvas.draw_idle()
        return

    dt  = sl_dt.val
    win = sl_win.val

    # build time axis
    t_all = [i * dt for i in range(n)]

    if show_all[0]:
        sl = slice(None)
        ts = t_all
    else:
        # find how many samples fit in the time window
        w = max(1, int(win / dt))
        s = max(0, n - w)
        sl = slice(s, None)
        ts = t_all[s:]

    rx  = data["rx"][sl];  ry  = data["ry"][sl]
    rvx = data["rvx"][sl]; rvy = data["rvy"][sl]
    fx  = data["fx"][sl];  fy  = data["fy"][sl]
    fvx = data["fvx"][sl]; fvy = data["fvy"][sl]

    ln_rx_pos.set_data(ts, rx);   ln_rx_vel.set_data(ts, rvx)
    ln_fx_pos.set_data(ts, fx);   ln_fx_vel.set_data(ts, fvx)
    ln_ry_pos.set_data(ts, ry);   ln_ry_vel.set_data(ts, rvy)
    ln_fy_pos.set_data(ts, fy);   ln_fy_vel.set_data(ts, fvy)

    for ax in [ax_rx, ax_fx, ax_ry, ax_fy,
               ax_rx2, ax_fx2, ax_ry2, ax_fy2]:
        ax.relim()
        ax.autoscale_view()

    debug_t.set_text(
        f"lines read: {stats['total']}  paired: {stats['paired']}  "
        f"unpaired filtered: {stats['unpaired_f']}  unpaired normal: {stats['unpaired_n']}"
    )
    status.set_text(
        f"samples: {n}  |  time span: {t_all[-1]:.2f}s  |  showing: {len(ts)} samples  |  "
        f"raw x={data['rx'][-1]:.3f} y={data['ry'][-1]:.3f}  |  "
        f"kalman x={data['fx'][-1]:.3f} y={data['fy'][-1]:.3f}  "
        f"vx={data['fvx'][-1]:.3f} vy={data['fvy'][-1]:.3f}"
    )
    fig.canvas.draw_idle()

def animate(_):
    if read_new_lines():
        redraw()

ani = animation.FuncAnimation(
    fig, animate, interval=200, blit=False, cache_frame_data=False
)

print(f"Watching '{FILE_PATH}'")
print("Adjust dt to match your actual sample rate. Window slider controls how many seconds are shown.")
plt.show()
