import { createChart } from './chart.js';
import { createTrajectoryChart } from './trajectory.js';

const axisCards = document.getElementById('axisCards');
const sourceLabel = document.getElementById('sourceLabel');
const sampleCount = document.getElementById('sampleCount');
const updatedAt = document.getElementById('updatedAt');
const connectionPill = document.getElementById('connectionPill');
const connectionState = document.getElementById('connectionState');
const loopTime = document.getElementById('loopTime');
const latestErrorX = document.getElementById('latestErrorX');
const latestErrorY = document.getElementById('latestErrorY');
const trajectoryBadge = document.getElementById('trajectoryBadge');
const responseBadge = document.getElementById('responseBadge');
const errorBadge = document.getElementById('errorBadge');

const trajectoryChart = createTrajectoryChart(document.getElementById('trajectoryChart'));

const responseChart = createChart(document.getElementById('responseChart'), {
  title: 'PID response',
  series: [
    { key: 'pidX', label: 'PidX', color: '#7ee0ff' },
    { key: 'pidY', label: 'PidY', color: '#8cf2b7' },
  ],
});

const errorChart = createChart(document.getElementById('errorChart'), {
  title: 'Error',
  series: [
    { key: 'errorX', label: 'Error X', color: '#ff8b8b' },
    { key: 'errorY', label: 'Error Y', color: '#f5c26b' },
  ],
});

let state = null;

function formatValue(value) {
  return Number.isFinite(value) ? value.toFixed(2) : '--';
}

function renderMetricCard(axisName, axis) {
  const delta = axis.error >= 0 ? 'delta-up' : 'delta-down';
  return `
    <article class="metric-card">
      <div class="metric-title">
        <strong>${axisName}</strong>
        <span>${axis.output != null ? `Output ${formatValue(axis.output)}` : 'Output --'}</span>
      </div>
      <div class="metric-value">${formatValue(axis.measurement)}</div>
      <div class="metric-subtitle">Setpoint ${formatValue(axis.setpoint)} <span class="${delta}">Error ${formatValue(axis.error)}</span></div>
    </article>
  `;
}

function applyState(snapshot) {
  state = snapshot || state;
  const latest = state?.latest || {};
  const axisX = latest.axisX || {};
  const axisY = latest.axisY || {};

  axisCards.innerHTML = [
    renderMetricCard('Axis X', axisX),
    renderMetricCard('Axis Y', axisY),
    `
      <article class="metric-card">
        <div class="metric-title"><strong>Loop time</strong><span>ms</span></div>
        <div class="metric-value">${formatValue(latest.loopTimeMs)}</div>
        <div class="metric-subtitle">Control loop cadence</div>
      </article>
    `,
    `
      <article class="metric-card">
        <div class="metric-title"><strong>Connection</strong><span>${state?.source || 'unknown'}</span></div>
        <div class="metric-value">${state?.source ? 'Live' : 'Idle'}</div>
        <div class="metric-subtitle">SSE + serial/HTTP ingest ready</div>
      </article>
    `,
  ].join('');

  sourceLabel.textContent = state?.source || '--';
  sampleCount.textContent = String(state?.samples ?? 0);
  updatedAt.textContent = state?.updatedAt ? new Date(state.updatedAt).toLocaleTimeString() : '--';
  loopTime.textContent = latest.loopTimeMs != null ? `${formatValue(latest.loopTimeMs)} ms` : '--';
  latestErrorX.textContent = axisX.error != null ? formatValue(axisX.error) : '--';
  latestErrorY.textContent = axisY.error != null ? formatValue(axisY.error) : '--';
  trajectoryBadge.textContent = `${formatValue(axisX.setpoint)} / ${formatValue(axisY.setpoint)}`;
  responseBadge.textContent = axisX.output != null && axisY.output != null
    ? `X ${formatValue(axisX.output)} | Y ${formatValue(axisY.output)}`
    : '--';
  errorBadge.textContent = axisX.error != null && axisY.error != null
    ? `X ${formatValue(axisX.error)} | Y ${formatValue(axisY.error)}`
    : '--';

  connectionState.textContent = state?.source ? `Connected via ${state.source}` : 'Waiting for telemetry';
  connectionPill.textContent = state?.source ? 'Live' : 'Waiting';
  connectionPill.style.background = state?.source ? 'rgba(140, 242, 183, 0.12)' : 'rgba(255, 255, 255, 0.06)';
  connectionPill.style.borderColor = state?.source ? 'rgba(140, 242, 183, 0.24)' : 'rgba(255, 255, 255, 0.08)';
  connectionPill.style.color = state?.source ? 'var(--accent-2)' : 'var(--muted)';

  const history = Array.isArray(state?.history) ? state.history : [];
  trajectoryChart.setData(history.map((frame) => ({
    setpointX: frame.axisX?.setpoint,
    setpointY: frame.axisY?.setpoint,
    measurementX: frame.axisX?.measurement,
    measurementY: frame.axisY?.measurement,
  })));
  responseChart.setData(history.map((frame) => ({
    pidX: frame.axisX?.output,
    pidY: frame.axisY?.output,
  })));
  errorChart.setData(history.map((frame) => ({
    errorX: frame.axisX?.error,
    errorY: frame.axisY?.error,
  })));
}

function pushFrame(frame) {
  if (!state) {
    return;
  }
  const history = Array.isArray(state.history) ? [...state.history, frame] : [frame];
  state = {
    ...state,
    latest: frame,
    history: history.slice(-360),
    updatedAt: frame.timestamp,
    samples: Math.max((state.samples ?? 0) + 1, history.length),
    source: frame.source || state.source,
  };
  applyState(state);
}

async function loadInitialState() {
  const response = await fetch('/api/state?limit=360');
  if (!response.ok) {
    throw new Error(`Failed to load state (${response.status})`);
  }
  return response.json();
}

function connectStream() {
  const source = new EventSource('/api/stream');
  source.addEventListener('snapshot', (event) => {
    applyState(JSON.parse(event.data));
  });
  source.addEventListener('frame', (event) => {
    pushFrame(JSON.parse(event.data));
  });
  source.onopen = () => {
    if (!state?.source) {
      connectionPill.textContent = 'Connected';
      connectionState.textContent = 'Live stream established';
    }
  };
  source.onerror = () => {
    connectionPill.textContent = 'Reconnecting';
    connectionState.textContent = 'Streaming reconnect in progress';
  };
}

async function bootstrap() {
  try {
    applyState(await loadInitialState());
  } catch (error) {
    connectionState.textContent = error.message;
    connectionPill.textContent = 'Offline';
  }
  connectStream();
}

bootstrap();