import serial
import matplotlib.pyplot as plt
from collections import deque

PORT = "COM5"      # change this
BAUD = 115200

ser = serial.Serial(PORT, BAUD, timeout=1)

N = 300
x_data = deque(maxlen=N)
y_data = deque(maxlen=N)

plt.ion()
fig, ax = plt.subplots()

sc = ax.scatter([], [], s=8)

ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.set_title("Touch Panel XY Live")
ax.set_xlabel("X")
ax.set_ylabel("Y")

while True:
    try:
        line = ser.readline().decode(errors="ignore").strip()

        if not line:
            continue

        # safety check
        if "," not in line:
            continue

        parts = line.split(",")

        if len(parts) != 2:
            continue

        x = float(parts[0])
        y = float(parts[1])

        x_data.append(x)
        y_data.append(y)

        # update scatter instead of redrawing plot
        sc.set_offsets(list(zip(x_data, y_data)))

        plt.pause(0.001)

    except KeyboardInterrupt:
        break

    except Exception as e:
        print("Error:", e)