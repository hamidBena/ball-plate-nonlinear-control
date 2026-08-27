import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.widgets import Slider, Button
import re
import time

# ── file to watch ────────────────────────────────────────────────────────────
FILE_PATH = "outputs/TouchReadingsV2.txt"

# ── initial tuning values ─────────────────────────────────────────────────────
INIT_VARIANCE_THRESH = 0.0001
INIT_DT              = 0.033
INIT_Q_POS           = 0.0035
INIT_Q_VEL           = 0.0107
INIT_R_NOISE         = 0.005

# ─────────────────────────────────────────────────────────────────────────────
# tuneable params (sliders write to these)
params = {
    "var_thresh" : INIT_VARIANCE_THRESH,
    "dt"         : INIT_DT,
    "q_pos"      : INIT_Q_POS,
    "q_vel"      : INIT_Q_VEL,
    "r_noise"    : INIT_R_NOISE,
}

# ─────────────────────────────────────────────────────────────────────────────
# raw file storage — we keep every parsed line forever so we can
# reprocess everything from scratch when a slider moves
all_raw_x = []   # averaged x per accepted line
all_raw_y = []
all_rejected = 0


def variance(values):
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)


def parse_line(line, var_thresh):
    """Return (avg_x, avg_y) or None if line is bad or variance too high."""
    match = re.search(
        r"normal X:\s*([\d.\s]+)\|\|\s*normal Y:\s*([\d.\s]+)",
        line
    )
    if not match:
        return None
    x_vals = [float(v) for v in match.group(1).split()]
    y_vals = [float(v) for v in match.group(2).split()]
    if not x_vals or not y_vals:
        return None
    if variance(x_vals) > var_thresh or variance(y_vals) > var_thresh:
        return None
    return sum(x_vals) / len(x_vals), sum(y_vals) / len(y_vals)


# ─────────────────────────────────────────────────────────────────────────────
# Kalman — scalar only, no matrices

def run_kalman(xs, ys, dt, q_pos, q_vel, r_noise):
    """
    Takes lists of accepted (avg_x, avg_y) readings.
    Returns (kal_x, kal_y, kal_vx, kal_vy) lists.
    """
    kx_pos = kx_vel = ky_pos = ky_vel = 0.0
    kx_ppos = kx_pvel = ky_ppos = ky_pvel = 1.0
    initialized = False

    out_x, out_y, out_vx, out_vy = [], [], [], []

    for mx, my in zip(xs, ys):
        if not initialized:
            kx_pos, ky_pos = mx, my
            kx_vel = ky_vel = 0.0
            kx_ppos = kx_pvel = ky_ppos = ky_pvel = 1.0
            initialized = True
        else:
            # ── predict ─────────────────────────────
            kx_pos  = kx_pos + kx_vel * dt
            ky_pos  = ky_pos + ky_vel * dt
            kx_ppos = kx_ppos + kx_pvel * dt * dt + q_pos
            kx_pvel = kx_pvel + q_vel
            ky_ppos = ky_ppos + ky_pvel * dt * dt + q_pos
            ky_pvel = ky_pvel + q_vel

            # ── update x ────────────────────────────
            k_pos_x   = kx_ppos / (kx_ppos + r_noise)
            k_vel_x   = kx_pvel * dt / (kx_ppos + r_noise)
            inn_x     = mx - kx_pos
            kx_pos    = kx_pos  + k_pos_x * inn_x
            kx_vel    = kx_vel  + k_vel_x * inn_x
            kx_ppos   = (1 - k_pos_x) * kx_ppos
            kx_pvel   = (1 - k_vel_x * dt) * kx_pvel

            # ── update y ────────────────────────────
            k_pos_y   = ky_ppos / (ky_ppos + r_noise)
            k_vel_y   = ky_pvel * dt / (ky_ppos + r_noise)
            inn_y     = my - ky_pos
            ky_pos    = ky_pos  + k_pos_y * inn_y
            ky_vel    = ky_vel  + k_vel_y * inn_y
            ky_ppos   = (1 - k_pos_y) * ky_ppos
            ky_pvel   = (1 - k_vel_y * dt) * ky_pvel

        out_x.append(kx_pos)
        out_y.append(ky_pos)
        out_vx.append(kx_vel)
        out_vy.append(ky_vel)

    return out_x, out_y, out_vx, out_vy


def compute_raw_velocity(xs, ys, dt):
    vx, vy = [0.0], [0.0]
    for i in range(1, len(xs)):
        vx.append((xs[i] - xs[i-1]) / dt)
        vy.append((ys[i] - ys[i-1]) / dt)
    return vx, vy


def reprocess():
    """Re-run variance filter + kalman on all stored file lines using current params."""
    vt  = params["var_thresh"]
    dt  = params["dt"]
    qp  = params["q_pos"]
    qv  = params["q_vel"]
    rn  = params["r_noise"]

    # re-apply variance filter to every raw stored line
    accepted_x, accepted_y = [], []
    rejected = 0
    for (rx, ry) in stored_lines:
        # stored_lines holds the raw value lists, not averages
        vx_var = variance(rx)
        vy_var = variance(ry)
        if vx_var > vt or vy_var > vt:
            rejected += 1
            continue
        accepted_x.append(sum(rx) / len(rx))
        accepted_y.append(sum(ry) / len(ry))

    if len(accepted_x) < 2:
        return [], [], [], [], [], [], [], [], 0, len(accepted_x)

    n = len(accepted_x)
    t = [i * dt for i in range(n)]
    raw_vx, raw_vy = compute_raw_velocity(accepted_x, accepted_y, dt)
    kal_x, kal_y, kal_vx, kal_vy = run_kalman(accepted_x, accepted_y, dt, qp, qv, rn)

    return (t, accepted_x, accepted_y, raw_vx, raw_vy,
            kal_x, kal_y, kal_vx, kal_vy, rejected, n)


# ─────────────────────────────────────────────────────────────────────────────
# file watcher state
stored_lines   = []   # list of ([x_vals], [y_vals]) for every valid-format line
last_file_pos  = 0
last_file_size = 0


def read_new_lines():
    global last_file_pos, last_file_size
    try:
        with open(FILE_PATH, "r") as f:
            f.seek(last_file_pos)
            new_lines = f.readlines()
            last_file_pos = f.tell()
    except FileNotFoundError:
        return False

    added = False
    for line in new_lines:
        line = line.strip()
        if not line:
            continue
        match = re.search(
            r"Raw X readings:\s*([\d.\s]+)\|\|\s*Raw Y readings:\s*([\d.\s]+)",
            line
        )
        if not match:
            continue
        x_vals = [float(v) for v in match.group(1).split()]
        y_vals = [float(v) for v in match.group(2).split()]
        if x_vals and y_vals:
            stored_lines.append((x_vals, y_vals))
            added = True

    return added


# ─────────────────────────────────────────────────────────────────────────────
# layout: tall figure, plots on top, sliders on bottom

fig = plt.figure(figsize=(14, 9))
fig.patch.set_facecolor("#f5f5f5")
fig.suptitle("Kalman filter visualiser  —  raw vs filtered", fontsize=13, y=0.98)

# plot axes
ax_rpos  = fig.add_axes([0.05, 0.62, 0.42, 0.30])   # raw position
ax_kpos  = fig.add_axes([0.55, 0.62, 0.42, 0.30])   # kalman position
ax_rvel  = fig.add_axes([0.05, 0.30, 0.42, 0.26])   # raw velocity
ax_kvel  = fig.add_axes([0.55, 0.30, 0.42, 0.26])   # kalman velocity

for ax in [ax_rpos, ax_kpos, ax_rvel, ax_kvel]:
    ax.set_facecolor("#ffffff")
    ax.grid(True, linestyle="--", alpha=0.35, color="#aaa")

ax_rpos.set_title("Raw sensor — position",  fontsize=10)
ax_kpos.set_title("Kalman — position",       fontsize=10)
ax_rvel.set_title("Raw sensor — velocity (finite diff)",  fontsize=10)
ax_kvel.set_title("Kalman — velocity (estimated)",        fontsize=10)

for ax in [ax_rpos, ax_kpos]:
    ax.set_ylabel("position (m)", fontsize=8)
for ax in [ax_rvel, ax_kvel]:
    ax.set_ylabel("velocity (m/s)", fontsize=8)
for ax in [ax_rvel, ax_kvel]:
    ax.set_xlabel("time (s)", fontsize=8)

BLUE  = "#378ADD"
GREEN = "#1D9E75"

ln_rpos_x, = ax_rpos.plot([], [], color=BLUE,  lw=1.4, label="X")
ln_rpos_y, = ax_rpos.plot([], [], color=GREEN, lw=1.4, label="Y")
ln_kpos_x, = ax_kpos.plot([], [], color=BLUE,  lw=1.4, label="X")
ln_kpos_y, = ax_kpos.plot([], [], color=GREEN, lw=1.4, label="Y")
ln_rvel_x, = ax_rvel.plot([], [], color=BLUE,  lw=1.0, label="Vx", alpha=0.8)
ln_rvel_y, = ax_rvel.plot([], [], color=GREEN, lw=1.0, label="Vy", alpha=0.8)
ln_kvel_x, = ax_kvel.plot([], [], color=BLUE,  lw=1.4, label="Vx")
ln_kvel_y, = ax_kvel.plot([], [], color=GREEN, lw=1.4, label="Vy")

for ax in [ax_rpos, ax_kpos, ax_rvel, ax_kvel]:
    ax.legend(fontsize=8, loc="upper left")

status_text = fig.text(0.05, 0.275, "", fontsize=8, color="#555", family="monospace")

# ─────────────────────────────────────────────────────────────────────────────
# sliders

slider_color = "#e8e8e8"

def make_slider(left, bottom, label, valmin, valmax, valinit, valfmt="%0.5f"):
    ax_s = fig.add_axes([left, bottom, 0.38, 0.022], facecolor=slider_color)
    s = Slider(ax_s, label, valmin, valmax, valinit=valinit, valfmt=valfmt, color=BLUE)
    s.label.set_fontsize(8)
    s.valtext.set_fontsize(8)
    return s

sl_var  = make_slider(0.05, 0.225, "Variance thresh", 0.00001, 0.005,  INIT_VARIANCE_THRESH)
sl_dt   = make_slider(0.55, 0.225, "dt (s)",          0.005,   0.2,    INIT_DT,    "%0.4f")
sl_qpos = make_slider(0.05, 0.185, "Q position",      0.00001, 0.05,   INIT_Q_POS)
sl_qvel = make_slider(0.55, 0.185, "Q velocity",      0.00001, 0.1,    INIT_Q_VEL)
sl_r    = make_slider(0.05, 0.145, "R noise",         0.00001, 0.01,   INIT_R_NOISE)

# reset button
ax_btn = fig.add_axes([0.82, 0.14, 0.1, 0.032])
btn_reset = Button(ax_btn, "Reset sliders", color="#ddd", hovercolor="#bbb")

def on_reset(_):
    sl_var.reset()
    sl_dt.reset()
    sl_qpos.reset()
    sl_qvel.reset()
    sl_r.reset()

btn_reset.on_clicked(on_reset)

def slider_changed(_):
    params["var_thresh"] = sl_var.val
    params["dt"]         = sl_dt.val
    params["q_pos"]      = sl_qpos.val
    params["q_vel"]      = sl_qvel.val
    params["r_noise"]    = sl_r.val
    redraw()

for sl in [sl_var, sl_dt, sl_qpos, sl_qvel, sl_r]:
    sl.on_changed(slider_changed)


def redraw():
    result = reprocess()
    if not result or len(result[0]) == 0:
        status_text.set_text(f"samples: {len(stored_lines)} total  |  waiting for data...")
        fig.canvas.draw_idle()
        return

    (t, acc_x, acc_y, raw_vx, raw_vy,
     kal_x, kal_y, kal_vx, kal_vy, rejected, accepted) = result

    ln_rpos_x.set_data(t, acc_x)
    ln_rpos_y.set_data(t, acc_y)
    ln_kpos_x.set_data(t, kal_x)
    ln_kpos_y.set_data(t, kal_y)
    ln_rvel_x.set_data(t, raw_vx)
    ln_rvel_y.set_data(t, raw_vy)
    ln_kvel_x.set_data(t, kal_vx)
    ln_kvel_y.set_data(t, kal_vy)

    for ax in [ax_rpos, ax_kpos, ax_rvel, ax_kvel]:
        ax.relim()
        ax.autoscale_view()

    status_text.set_text(
        f"file lines read: {len(stored_lines)}  |  accepted: {accepted}  |  "
        f"rejected (variance): {rejected}  |  "
        f"last pos  x={kal_x[-1]:.4f}  y={kal_y[-1]:.4f}  "
        f"vel_x={kal_vx[-1]:.4f}  vel_y={kal_vy[-1]:.4f}"
    )
    fig.canvas.draw_idle()


# ─────────────────────────────────────────────────────────────────────────────
# animation loop — checks file every 300ms

def animate(_frame):
    added = read_new_lines()
    if added:
        redraw()

ani = animation.FuncAnimation(
    fig, animate, interval=300, blit=False, cache_frame_data=False
)

print(f"Watching '{FILE_PATH}' for new lines...")
print("Move the sliders to retune in real time. All data is reprocessed instantly.")
plt.show()
