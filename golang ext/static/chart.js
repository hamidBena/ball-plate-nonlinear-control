const palette = ['#7ee0ff', '#8cf2b7', '#ff8b8b'];

export function createChart(canvas, options) {
  const context = canvas.getContext('2d');
  let points = [];

  function resizeForDpr() {
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.getBoundingClientRect().width;
    const height = width * 0.375;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    canvas.style.height = `${height}px`;
  }

  function drawGrid(width, height) {
    context.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    context.lineWidth = 1;
    context.beginPath();
    for (let i = 0; i <= 6; i += 1) {
      const x = 56 + ((width - 90) / 6) * i;
      context.moveTo(x, 20);
      context.lineTo(x, height - 36);
    }
    for (let i = 0; i <= 4; i += 1) {
      const y = 20 + ((height - 56) / 4) * i;
      context.moveTo(56, y);
      context.lineTo(width - 24, y);
    }
    context.stroke();
  }

  function drawAxes(width, height, minValue, maxValue) {
    context.fillStyle = 'rgba(232, 238, 249, 0.65)';
    context.font = '12px var(--font)';
    context.fillText(options.title, 20, 18);
    context.fillText(maxValue.toFixed(1), 12, 32);
    context.fillText(((maxValue + minValue) / 2).toFixed(1), 8, height / 2);
    context.fillText(minValue.toFixed(1), 12, height - 18);
  }

  function seriesBounds(series) {
    const values = series.flatMap((entry) => [entry.setpoint, entry.measurement, entry.error]).filter(Number.isFinite);
    if (!values.length) {
      return { min: -1, max: 1 };
    }
    const min = Math.min(...values);
    const max = Math.max(...values);
    if (min === max) {
      return { min: min - 1, max: max + 1 };
    }
    const padding = Math.max((max - min) * 0.12, 1);
    return { min: min - padding, max: max + padding };
  }

  function drawLine(series, key, color, dashed, width, height, minValue, maxValue) {
    const plotWidth = width - 90;
    const plotHeight = height - 56;
    const left = 56;
    const top = 20;
    const usablePoints = series.filter((entry) => Number.isFinite(entry[key]));
    if (usablePoints.length < 2) {
      return;
    }

    context.beginPath();
    context.strokeStyle = color;
    context.lineWidth = 2.2;
    context.setLineDash(dashed ? [8, 8] : []);
    usablePoints.forEach((entry, index) => {
      const x = left + (plotWidth * index) / (usablePoints.length - 1);
      const normalized = (entry[key] - minValue) / (maxValue - minValue);
      const y = top + plotHeight - normalized * plotHeight;
      if (index === 0) {
        context.moveTo(x, y);
      } else {
        context.lineTo(x, y);
      }
    });
    context.stroke();
    context.setLineDash([]);
  }

  function drawLegend() {
    let x = 58;
    const y = 20;
    options.series.forEach((item, index) => {
      context.fillStyle = item.color || palette[index % palette.length];
      context.fillRect(x, y - 8, 10, 10);
      context.fillStyle = 'rgba(232, 238, 249, 0.75)';
      context.fillText(item.label, x + 16, y);
      x += context.measureText(item.label).width + 52;
    });
  }

  function render() {
    resizeForDpr();
    const width = canvas.getBoundingClientRect().width;
    const height = canvas.getBoundingClientRect().height;
    context.clearRect(0, 0, width, height);

    const bounds = seriesBounds(points);
    drawGrid(width, height);
    drawAxes(width, height, bounds.min, bounds.max);
    drawLegend();

    options.series.forEach((item, index) => {
      drawLine(points, item.key, item.color || palette[index % palette.length], item.dashed, width, height, bounds.min, bounds.max);
    });
  }

  window.addEventListener('resize', render);

  return {
    setData(nextPoints) {
      points = Array.isArray(nextPoints) ? nextPoints : [];
      render();
    },
  };
}