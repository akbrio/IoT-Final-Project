/* ------------------------------------------------------------------ *
 * Generator Monitor — live dashboard
 * Builds one cell + chart per sensor (from /api/sensors), loads history
 * for the selected window, and streams live readings over a WebSocket.
 * ------------------------------------------------------------------ */

const state = {
  sensors: [], charts: {}, data: {}, stats: {},
  windowMin: 5, ws: null,
};

function fmt(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const abs = Math.abs(v);
  if (abs >= 1000) return v.toFixed(0);
  if (abs >= 100)  return v.toFixed(1);
  return v.toFixed(2);
}

function fmtTime(ms) {
  const d = new Date(ms);
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

/* ---------- chart ---------- */
function makeChart(canvas, color) {
  const ctx = canvas.getContext("2d");
  const grad = ctx.createLinearGradient(0, 0, 0, 128);
  grad.addColorStop(0, color + "33");
  grad.addColorStop(1, color + "00");

  return new Chart(ctx, {
    type: "line",
    data: { datasets: [{
      data: [],
      borderColor: color,
      backgroundColor: grad,
      borderWidth: 1.7,
      pointRadius: 0,
      tension: 0.32,
      fill: true,
    }]},
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      parsing: false,
      interaction: { mode: "nearest", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#0e1113",
          borderColor: "#252b30",
          borderWidth: 1,
          padding: 9,
          titleColor: "#93a0a7",
          titleFont: { family: "JetBrains Mono", size: 10 },
          bodyColor: "#eef2f4",
          bodyFont: { family: "JetBrains Mono", size: 13, weight: "600" },
          displayColors: false,
          callbacks: {
            title: (i) => fmtTime(i[0].parsed.x),
            label: (i) => fmt(i.parsed.y),
          },
        },
      },
      scales: {
        x: {
          type: "linear",
          border: { display: false },
          ticks: {
            color: "#5d676d",
            font: { family: "JetBrains Mono", size: 10 },
            maxRotation: 0, autoSkip: true, maxTicksLimit: 5,
            callback: (v) => fmtTime(v),
          },
          grid: { color: "rgba(255,255,255,0.035)" },
        },
        y: {
          border: { display: false },
          ticks: {
            color: "#5d676d",
            font: { family: "JetBrains Mono", size: 10 },
            maxTicksLimit: 4,
          },
          grid: { color: "rgba(255,255,255,0.035)" },
        },
      },
    },
  });
}

/* ---------- cells ---------- */
function buildCells() {
  const board = document.getElementById("grid");
  board.innerHTML = "";

  state.sensors.forEach((s) => {
    state.data[s.key] = [];
    state.stats[s.key] = { min: null, max: null };

    const cell = document.createElement("article");
    cell.className = "cell";
    cell.style.setProperty("--accent", s.color);
    cell.innerHTML = `
      <div class="cell-top">
        <span class="cell-label"><span class="tick"></span>${s.label}</span>
        <span class="cell-topic">${s.topic}</span>
      </div>
      <div class="cell-readout">
        <span class="cell-value" id="val-${s.key}">—</span>
        <span class="cell-unit">${s.unit}</span>
      </div>
      <div class="cell-chart"><canvas id="chart-${s.key}"></canvas></div>
      <div class="cell-foot">
        <span><i>Min</i><b id="min-${s.key}">—</b></span>
        <span><i>Max</i><b id="max-${s.key}">—</b></span>
      </div>
    `;
    board.appendChild(cell);
    state.charts[s.key] = makeChart(cell.querySelector(`#chart-${s.key}`), s.color);
  });
}

/* ---------- history ---------- */
async function loadHistory() {
  await Promise.all(state.sensors.map(async (s) => {
    try {
      const res = await fetch(`/api/history?sensor=${s.key}&minutes=${state.windowMin}`);
      const json = await res.json();
      state.data[s.key] = json.points.map((p) => ({ x: p.ts, y: p.value }));
      recomputeStats(s.key);
      pushToChart(s.key);
      updateReadout(s.key);
    } catch (e) {
      console.error("history load failed for", s.key, e);
    }
  }));
}

function windowFloor() { return Date.now() - state.windowMin * 60 * 1000; }

function trim(key) {
  const floor = windowFloor();
  const arr = state.data[key];
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
  if (arr.length) document.getElementById(`val-${key}`).textContent = fmt(arr[arr.length - 1].y);
  document.getElementById(`min-${key}`).textContent = fmt(state.stats[key].min);
  document.getElementById(`max-${key}`).textContent = fmt(state.stats[key].max);
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
  document.getElementById("last-update").textContent = "Updated " + fmtTime(ts);
}

setInterval(() => {
  state.sensors.forEach((s) => {
    trim(s.key); recomputeStats(s.key); pushToChart(s.key); updateReadout(s.key);
  });
}, 5000);

/* ---------- connection state ---------- */
function setStatus(stateName, label) {
  const el = document.getElementById("status");
  el.dataset.state = stateName;
  el.querySelector(".link-label").textContent = label;
}

function connectWS() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  state.ws = ws;
  ws.onopen = () => setStatus("live", "Live");
  ws.onmessage = (e) => { try { onReading(JSON.parse(e.data)); } catch (_) {} };
  ws.onclose = () => { setStatus("down", "Reconnecting"); setTimeout(connectWS, 2000); };
  ws.onerror = () => ws.close();
}

/* ---------- window selector ---------- */
function initWindowSelector() {
  const box = document.getElementById("window-select");
  box.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    box.querySelectorAll("button").forEach((b) => b.classList.remove("is-active"));
    btn.classList.add("is-active");
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
      '<p class="placeholder">Could not load the sensor list. Is the server running?</p>';
    return;
  }

  document.getElementById("topic-list").textContent =
    "Topics   " + state.sensors.map((s) => s.topic).join("   ·   ");

  buildCells();
  initWindowSelector();
  await loadHistory();
  connectWS();
}

init();
