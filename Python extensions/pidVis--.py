import re
import matplotlib.pyplot as plt

FILENAME = "PID.txt"

setpoint_re = re.compile(
    r"Setpoints:\s*\(([-\d.]+),\s*([-\d.]+)\)\s*\|\s*Measurements:\s*\(([-\d.]+),\s*([-\d.]+)\)\s*\|\s*PidX:\s*([-\d.]+)\s*\|\s*PidY:\s*([-\d.]+)"
)
pidx_re = re.compile(r"Px:\s*\(([-\d.]+)\)\s*\|\s*Ix:\s*\(([-\d.]+)\)\s*\|\s*Dx:\s*([-\d.]+)")
pidy_re = re.compile(r"Py:\s*\(([-\d.]+)\)\s*\|\s*Iy:\s*\(([-\d.]+)\)\s*\|\s*Dy:\s*([-\d.]+)")

setpoints_x, setpoints_y = [], []
meas_x, meas_y = [], []
pid_x, pid_y = [], []
px, ix, dx = [], [], []
py, iy, dy = [], [], []

with open(FILENAME) as f:
    for line in f:
        m = setpoint_re.search(line)
        if m:
            sx, sy, mx, my, ox, oy = map(float, m.groups())
            setpoints_x.append(sx)
            setpoints_y.append(sy)
            meas_x.append(mx)
            meas_y.append(my)
            pid_x.append(ox)
            pid_y.append(oy)
            continue

        m = pidx_re.search(line)
        if m:
            p, i, d = map(float, m.groups())
            px.append(p)
            ix.append(i)
            dx.append(d)
            continue

        m = pidy_re.search(line)
        if m:
            p, i, d = map(float, m.groups())
            py.append(p)
            iy.append(i)
            dy.append(d)
            continue

n = len(setpoints_x)
print(f"Loaded {n} samples")

error_x = [m - s for m, s in zip(meas_x, setpoints_x)]
error_y = [m - s for m, s in zip(meas_y, setpoints_y)]

fig, axes = plt.subplots(4, 2, figsize=(14, 16))

# Setpoints vs Measurements
axes[0, 0].plot(setpoints_x, label="Setpoint X")
axes[0, 0].plot(meas_x, label="Measurement X")
axes[0, 0].set_title("X: Setpoint vs Measurement")
axes[0, 0].legend()

axes[0, 1].plot(setpoints_y, label="Setpoint Y")
axes[0, 1].plot(meas_y, label="Measurement Y")
axes[0, 1].set_title("Y: Setpoint vs Measurement")
axes[0, 1].legend()

# Error
axes[1, 0].plot(error_x, color="tab:red")
axes[1, 0].set_title("Error X (measurement - setpoint)")
axes[1, 0].axhline(0, color="black", linewidth=0.5)

axes[1, 1].plot(error_y, color="tab:red")
axes[1, 1].set_title("Error Y (measurement - setpoint)")
axes[1, 1].axhline(0, color="black", linewidth=0.5)

# PID outputs
axes[2, 0].plot(pid_x, color="tab:purple")
axes[2, 0].set_title("PidX output")

axes[2, 1].plot(pid_y, color="tab:purple")
axes[2, 1].set_title("PidY output")

# Internal P/I/D components
axes[3, 0].plot(px, label="P")
axes[3, 0].plot(ix, label="I")
axes[3, 0].plot(dx, label="D")
axes[3, 0].set_title("PidX components")
axes[3, 0].legend()

axes[3, 1].plot(py, label="P")
axes[3, 1].plot(iy, label="I")
axes[3, 1].plot(dy, label="D")
axes[3, 1].set_title("PidY components")
axes[3, 1].legend()

for row in axes:
    for ax in row:
        ax.set_xlabel("Sample index")

plt.tight_layout()
plt.savefig("pid_plots.png", dpi=150)
plt.show()