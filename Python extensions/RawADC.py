import re
import statistics
import matplotlib.pyplot as plt

FILENAME = "outputs/TouchReadingsV2.txt"
TAIL_START = 5  # skip the expected settling samples

x_series, y_series = [], []
rejected_flags = []  # True if "High noise detected" line follows this reading set

reading_re = re.compile(r"Raw X readings:\s*(.*?)\s*\|\|\s*Raw Y readings:\s*(.*)")
noise_re = re.compile(r"High noise detected! X stddev: ([\d.]+) \| Y stddev: ([\d.]+)")

with open(FILENAME) as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    m = reading_re.search(line)
    if m:
        x_vals = [float(v) for v in m.group(1).split()]
        y_vals = [float(v) for v in m.group(2).split()]
        x_series.append(x_vals)
        y_series.append(y_vals)

        # check if the *next* line is a "High noise detected" message
        rejected = False
        if i + 1 < len(lines) and noise_re.search(lines[i + 1]):
            rejected = True
        rejected_flags.append(rejected)

print(f"Loaded {len(x_series)} reading sets, {sum(rejected_flags)} rejected")

fig, axes = plt.subplots(1, 2, figsize=(12, 5))

for x_vals, rejected in zip(x_series, rejected_flags):
    color = "red" if rejected else "tab:blue"
    alpha = 0.8 if rejected else 0.2
    lw = 2 if rejected else 1
    axes[0].plot(x_vals, color=color, alpha=alpha, linewidth=lw)

for y_vals, rejected in zip(y_series, rejected_flags):
    color = "red" if rejected else "tab:blue"
    alpha = 0.8 if rejected else 0.2
    lw = 2 if rejected else 1
    axes[1].plot(y_vals, color=color, alpha=alpha, linewidth=lw)

axes[0].set_title("Raw X readings (red = rejected, high noise)")
axes[0].set_xlabel("Sample index")
axes[0].set_ylabel("Value")

axes[1].set_title("Raw Y readings (red = rejected, high noise)")
axes[1].set_xlabel("Sample index")
axes[1].set_ylabel("Value")

plt.tight_layout()
plt.savefig("readings_rejected.png", dpi=150)
plt.show()