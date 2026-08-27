export function createTrajectoryChart(canvas) {
  const context = canvas.getContext('2d');
  let points = [];

  function resizeForDpr() {
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.getBoundingClientRect().width;
    const height = Math.max(420, width * 0.52);
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    canvas.style.height = `${height}px`;
  }

  function chartBounds() {
    const values = points.flatMap((entry) => [entry.setpointX, entry.setpointY, entry.measurementX, entry.measurementY]).filter(Number.isFinite);
    if (values.length === 0) {
      return { min: -1, max: 1 };
    }
    const min = Math.min(...values);
    const max = Math.max(...values);
    const padding = Math.max((max - min) * 0.12, 1);
    return { min: min - padding, max: max + padding };
  }

  function mapPoint(value, min, max, start, size) {
    if (!Number.isFinite(value)) {
      return null;
    }
    return start + ((value - min) / (max - min)) * size;
  }

  function drawAxes(width, height, min, max) {
    const left = 72;
    const top = 28;
    const plotWidth = width - 108;
    const plotHeight = height - 92;

    context.strokeStyle = 'rgba(255, 255, 255, 0.08)';
    context.lineWidth = 1;
    context.beginPath();
    for (let i = 0; i <= 6; i += 1) {
      const x = left + (plotWidth / 6) * i;
      context.moveTo(x, top);
      context.lineTo(x, top + plotHeight);
    }
    for (let i = 0; i <= 6; i += 1) {
      const y = top + (plotHeight / 6) * i;
      context.moveTo(left, y);
      context.lineTo(left + plotWidth, y);
    }
    context.stroke();

    context.fillStyle = 'rgba(232, 238, 249, 0.72)';
    context.font = '12px var(--font)';
    context.fillText('measurement Y', 16, 22);
    context.fillText('measurement X', width - 118, height - 16);
    context.fillText(max.toFixed(1), 12, top + 10);
    context.fillText(min.toFixed(1), 12, top + plotHeight);
  }

  function drawPath(series, keyX, keyY, color, width, height, min, max, dashed) {
    const left = 72;
    const top = 28;
    const plotWidth = width - 108;
    const plotHeight = height - 92;
    const usable = series.filter((entry) => Number.isFinite(entry[keyX]) && Number.isFinite(entry[keyY]));
    if (usable.length < 2) {
      return;
    }

    context.beginPath();
    context.strokeStyle = color;
    context.fillStyle = color;
    context.lineWidth = 2.2;
    context.setLineDash(dashed ? [10, 8] : []);

    usable.forEach((entry, index) => {
      const x = mapPoint(entry[keyX], min, max, left, plotWidth);
      const y = mapPoint(entry[keyY], min, max, top + plotHeight, -plotHeight);
      if (x == null || y == null) {
        return;
      }
      if (index === 0) {
        context.moveTo(x, y);
      } else {
        context.lineTo(x, y);
      }
    });
    context.stroke();

    usable.forEach((entry, index) => {
      if (index % Math.max(1, Math.floor(usable.length / 24)) !== 0) {
        return;
      }
      const x = mapPoint(entry[keyX], min, max, left, plotWidth);
      const y = mapPoint(entry[keyY], min, max, top + plotHeight, -plotHeight);
      if (x == null || y == null) {
        return;
      }
      context.beginPath();
      context.arc(x, y, dashed ? 4 : 3.5, 0, Math.PI * 2);
      context.fill();
    });

    context.setLineDash([]);
  }

  function drawTarget(series, width, height, min, max) {
    const latest = series.at(-1);
    if (!latest || !Number.isFinite(latest.setpointX) || !Number.isFinite(latest.setpointY)) {
      return;
    }

    const left = 72;
    const top = 28;
    const plotWidth = width - 108;
    const plotHeight = height - 92;
    const x = mapPoint(latest.setpointX, min, max, left, plotWidth);
    const y = mapPoint(latest.setpointY, min, max, top + plotHeight, -plotHeight);
    if (x == null || y == null) {
      return;
    }

    context.strokeStyle = 'rgba(126, 224, 255, 0.85)';
    context.fillStyle = 'rgba(126, 224, 255, 0.18)';
    context.lineWidth = 2;
    context.beginPath();
    context.arc(x, y, 10, 0, Math.PI * 2);
    context.fill();
    context.stroke();

    context.fillStyle = 'rgba(126, 224, 255, 0.9)';
    context.beginPath();
    context.arc(x, y, 3.5, 0, Math.PI * 2);
    context.fill();
  }

  function render() {
    resizeForDpr();
    const width = canvas.getBoundingClientRect().width;
    const height = canvas.getBoundingClientRect().height;
    const { min, max } = chartBounds();

    context.clearRect(0, 0, width, height);
    context.fillStyle = 'rgba(232, 238, 249, 0.84)';
    context.font = '13px var(--font)';
    context.fillText('Setpoint', 76, 20);
    context.fillStyle = 'rgba(140, 242, 183, 0.84)';
    context.fillText('Measurement', 164, 20);

    drawAxes(width, height, min, max);
    drawPath(points, 'setpointX', 'setpointY', 'rgba(126, 224, 255, 0.75)', width, height, min, max, true);
    drawPath(points, 'measurementX', 'measurementY', 'rgba(140, 242, 183, 0.9)', width, height, min, max, false);
    drawTarget(points, width, height, min, max);
  }

  window.addEventListener('resize', render);

  return {
    setData(nextPoints) {
      points = Array.isArray(nextPoints) ? nextPoints : [];
      render();
    },
  };
}