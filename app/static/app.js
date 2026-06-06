/* ------------------------------------------------------------------ *
 * GENSET Telemetry dashboard
 * - Builds one panel + live chart per sensor (from /api/sensors)
 * - Loads history for the selected time window
 * - Streams live readings over a WebSocket and appends them to the charts
 * ------------------------------------------------------------------ */

const state = {
  sensors: [],          // metadata from the API
  charts: {},           // key -> Chart instance
  data: {},             // key -> [{x: ms, y: value}, ...]
  stats: {},            // key -> {min, max}
  windowMin: 5,         // currently selected window in minutes
  ws: null,
};

/* ---------- number formatting ---------- */
function fmt(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return "--";
  const abs = Math.abs(v);
  if (abs >= 1000) return v.toFixed(0);
  if (abs >= 100)  return v.toFixed(1);
  return v.toFixed(2);
}

function fmtTime(ms) {
  const d = new Date(ms);
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/* ---------- build a chart ---------- */
function makeChart(canvas, color) {
  const ctx = canvas.getContext("2d");
  const grad = ctx.createLinearGradient(0, 0, 0, 180);
  grad.addColorStop(0, color + "55");
  grad.addColorStop(1, color + "00");

  return new Chart(ctx, {
    type: "line",
    data: {
      datasets: [{
        data: [],
        borderColor: color,
        backgroundColor: grad,
        borderWidth: 1.6,
        pointRadius: 0,
        tension: 0.25,
        fill: true,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      parsing: false,            // we feed {x, y} directly
      interaction: { mode: "nearest", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#0a0e0f",
          borderColor: color,
          borderWidth: 1,
          titleColor: "#9fb4b0",
          bodyColor: "#d7e4e2",
          displayColors: false,
          callbacks: {
            title: (items) => fmtTime(items[0].parsed.x),
            label: (item) => fmt(item.parsed.y),
          },
        },
      },
      scales: {
        x: {
          type: "linear",
          ticks: {
            color: "#42534f",
            font: { family: "IBM Plex Mono", size: 10 },
            maxRotation: 0,
            autoSkip: true,
            maxTicksLimit: 6,
            callback: (val) => fmtTime(val),
          },
          grid: { color: "#16211f" },
        },
        y: {
          ticks: {
            color: "#42534f",
            font: { family: "IBM Plex Mono", size: 10 },
            maxTicksLimit: 5,
          },
          grid: { color: "#16211f" },
        },
      },
    },
  });
}

/* ---------- panels ---------- */
function buildPanels() {
  const grid = document.getElementById("grid");
  grid.innerHTML = "";

  state.sensors.forEach((s) => {
    state.data[s.key] = [];
    state.stats[s.key] = { min: null, max: null };

    const panel = document.createElement("section");
    panel.className = "panel";
    panel.style.setProperty("--accent", s.color);
    panel.innerHTML = `
      <div class="panel-head">
        <span class="panel-title">${s.label}</span>
        <span class="panel-topic">${s.topic}</span>
      </div>
      <div class="readout">
        <span class="value" id="val-${s.key}">--</span>
        <span class="unit">${s.unit}</span>
        <div class="stats">
          <div class="stat"><div class="k">MIN</div><div class="v" id="min-${s.key}">--</div></div>
          <div class="stat"><div class="k">MAX</div><div class="v" id="max-${s.key}">--</div></div>
        </div>
      </div>
      <div class="chart-wrap"><canvas id="chart-${s.key}"></canvas></div>
    `;
    grid.appendChild(panel);

    const canvas = panel.querySelector(`#chart-${s.key}`);
    state.charts[s.key] = makeChart(canvas, s.color);
  });
}

/* ---------- history load ---------- */
async function loadHistory() {
  await Promise.all(state.sensors.map(async (s) => {
    try {
      const res = await fetch(`/api/history?sensor=${s.key}&minutes=${state.windowMin}`);
      const json = await res.json();
      const pts = json.points.map((p) => ({ x: p.ts, y: p.value }));
      state.data[s.key] = pts;
      recomputeStats(s.key);
      pushToChart(s.key);
      updateReadout(s.key);
    } catch (e) {
      console.error("history load failed for", s.key, e);
    }
  }));
}

function windowFloor() {
  return Date.now() - state.windowMin * 60 * 1000;
}

function trim(key) {
  const floor = windowFloor();
  const arr = state.data[key];
  // drop points older than the window
  let i = 0;
  while (i < arr.length && arr[i].x < floor) i++;
  if (i > 0) arr.splice(0, i);
}

function recomputeStats(key) {
  const arr = state.data[key];
  if (!arr.length) { state.stats[key] = { min: null, max: null }; return; }
  let mn = Infinity, mx = -Infinity;
  for (const p of arr) { if (p.y < mn) mn = p.y; if (p.y > mx) mx = p.y; }
  state.stats[key] = { min: mn, max: mx };
}

function pushToChart(key) {
  const chart = state.charts[key];
  chart.data.datasets[0].data = state.data[key];
  chart.update("none");
}

function updateReadout(key) {
  const arr = state.data[key];
  const valEl = document.getElementById(`val-${key}`);
  const minEl = document.getElementById(`min-${key}`);
  const maxEl = document.getElementById(`max-${key}`);
  if (arr.length) valEl.textContent = fmt(arr[arr.length - 1].y);
  minEl.textContent = fmt(state.stats[key].min);
  maxEl.textContent = fmt(state.stats[key].max);
}

/* ---------- live reading ---------- */
function onReading(msg) {
  const { sensor, value, ts } = msg;
  if (!state.data[sensor]) return;

  state.data[sensor].push({ x: ts, y: value });
  trim(sensor);

  const st = state.stats[sensor];
  st.min = st.min === null ? value : Math.min(st.min, value);
  st.max = st.max === null ? value : Math.max(st.max, value);

  pushToChart(sensor);
  updateReadout(sensor);

  document.getElementById("last-update").textContent =
    "last update " + fmtTime(ts);
}

/* periodically trim windows so old points scroll off even with no new data */
setInterval(() => {
  state.sensors.forEach((s) => {
    trim(s.key);
    recomputeStats(s.key);
    pushToChart(s.key);
    updateReadout(s.key);
  });
}, 5000);

/* ---------- WebSocket ---------- */
function setStatus(cls, text) {
  const el = document.getElementById("status");
  el.className = "status " + cls;
  el.querySelector(".status-text").textContent = text;
}

function connectWS() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  state.ws = ws;

  ws.onopen = () => setStatus("live", "LIVE");
  ws.onmessage = (e) => {
    try { onReading(JSON.parse(e.data)); } catch (_) {}
  };
  ws.onclose = () => {
    setStatus("down", "RECONNECTING");
    setTimeout(connectWS, 2000);   // auto-reconnect
  };
  ws.onerror = () => ws.close();
}

/* ---------- window selector ---------- */
function initWindowSelector() {
  const box = document.getElementById("window-select");
  box.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    box.querySelectorAll("button").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    state.windowMin = parseInt(btn.dataset.min, 10);
    loadHistory();
  });
}

/* ---------- boot ---------- */
async function init() {
  try {
    const res = await fetch("/api/sensors");
    state.sensors = await res.json();
  } catch (e) {
    document.getElementById("grid").innerHTML =
      '<div class="loading">Failed to load sensor list.</div>';
    return;
  }

  document.getElementById("broker-info").textContent =
    `${state.sensors.length} sensors · ${state.sensors.map((s) => s.topic).join("  ·  ")}`;

  buildPanels();
  initWindowSelector();
  await loadHistory();
  connectWS();
}

init();
