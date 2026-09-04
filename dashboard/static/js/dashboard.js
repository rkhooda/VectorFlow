/* SIH26153 dashboard — polling + panel rendering.
   Talks only to the Flask proxy (same origin); Flask forwards to FastAPI.
   All rendering is contract-driven: it consumes the backend response shapes
   from contracts/__init__.py and never mock implementation details. */

"use strict";

const POLL_MS = 2000; // matches replay.seconds_per_window

const state = {
  timer: null,
  observed: [],   // [{window, probability}] accumulated client-side during replay
  stageTrail: [], // tactic names in the order they appeared
  features: [],   // last explanation's contributions, most important first
  allFeatures: false, // "View All factors" toggle
  lastWindow: 0,
  finished: false,
};

const $ = (id) => document.getElementById(id);

async function api(path, options) {
  try {
    const resp = await fetch(path, options);
    let body = null;
    try { body = await resp.json(); } catch (_) { /* non-JSON body */ }
    return { ok: resp.ok, status: resp.status, body };
  } catch (_) {
    return { ok: false, status: 0, body: null };
  }
}

function showError(msg) {
  const el = $("error-banner");
  el.textContent = msg;
  el.hidden = false;
}
function clearError() { $("error-banner").hidden = true; }

/* ---------- polling ---------- */

function startPolling() {
  if (state.timer) clearInterval(state.timer);
  state.timer = setInterval(poll, POLL_MS);
  poll();
}

function stopPolling() {
  if (state.timer) clearInterval(state.timer);
  state.timer = null;
}

async function poll() {
  const st = await api("/api/session/status");

  if (st.status === 0 || st.status === 502) {
    showError("Backend unreachable — retrying…");
    return; // keep the last rendered data on screen
  }
  if (st.status === 404) { // no session yet
    renderStatus(null);
    stopPolling();
    return;
  }
  if (!st.ok) return;

  clearError();
  const status = st.body;
  renderStatus(status);

  if (status.state === "processing") return; // results not ready yet (409s)

  if (status.state === "replaying" || status.state === "completed") {
    await refreshResults(status);
    if (status.state === "completed" && !state.finished) {
      state.finished = true;
      stopPolling(); // final refresh above already rendered the last window
    }
  }
}

async function refreshResults(status) {
  const [forecast, stage, expl, flagged, traffic, netstate] = await Promise.all([
    api("/api/forecast"),
    api("/api/stage"),
    api("/api/explanations"),
    api("/api/flows/flagged"),
    api("/api/traffic/summary"),
    api("/api/state/current"),
  ]);
  // 409 = session no longer ready (e.g. restarted mid-poll): skip this round
  if (forecast.status === 409) return;

  if (forecast.ok) renderRisk(forecast.body, status);
  if (stage.ok) renderStage(stage.body);
  if (expl.ok) renderExplanations(expl.body);
  if (flagged.ok) renderFlagged(flagged.body);
  if (traffic.ok) renderTraffic(traffic.body);
  if (netstate.ok && forecast.ok) {
    recordObserved(status, forecast.body);
    renderTimeline(forecast.body, status);
  }
}

/* ---------- network status panel ---------- */

const STATE_PILLS = { replaying: "active", processing: "active", completed: "done", error: "bad" };

function renderStatus(status) {
  const pill = $("ns-state");
  if (!status) {
    pill.textContent = "no session";
    pill.className = "pill";
    $("ns-detail").textContent = "No session yet — upload a capture on the home page.";
    return;
  }
  $("ns-session").textContent = status.session_id;
  $("ns-input").textContent = status.input_file || "—";
  pill.textContent = status.state;
  pill.className = `pill ${STATE_PILLS[status.state] || ""}`;
  $("ns-window").textContent = status.total_windows
    ? `${status.current_window} / ${status.total_windows}` : "—";
  $("ns-progress").value = status.total_windows
    ? status.current_window / status.total_windows : 0;
  $("ns-detail").textContent = status.detail || "";
}

/* ---------- panel renderers (added per panel) ---------- */

function recordObserved(status, forecast) {
  if (status.current_window !== state.lastWindow) {
    state.lastWindow = status.current_window;
    state.observed.push({
      window: status.current_window,
      probability: forecast.infiltration_probability,
    });
  }
}

// presentation thresholds only — the prediction itself comes from the backend
const SEVERITIES = [
  [0.25, "Low", "low"],
  [0.5, "Moderate", "moderate"],
  [0.75, "High", "high"],
  [1.01, "Critical", "critical"],
];

function renderRisk(forecast) {
  const p = forecast.infiltration_probability;
  $("risk-value").textContent = `${(p * 100).toFixed(1)}%`;
  const [, label, cls] = SEVERITIES.find(([bound]) => p < bound);
  const pill = $("risk-severity");
  pill.textContent = `${label} risk`;
  pill.className = `pill ${cls}`;
  $("risk-model").textContent = forecast.model_name;
}

/* Risk-over-time chart. The x axis is seconds relative to the current replay
   position: observed windows run negative, the forecast horizon positive. */

const SEC_PER_WINDOW = POLL_MS / 1000; // mirrors replay.seconds_per_window
const PLOT = { l: 45, r: 766, t: 32, b: 324 }; // inside the 794x372 viewBox

// smallest step that keeps the axis under ~7 labels
const niceStep = (span) =>
  [5, 10, 20, 30, 60, 120, 300].find((s) => span / s <= 7) || 600;

// quadratic segments through the midpoints — a smooth curve without a library
function smoothPath(pts) {
  if (pts.length < 3) return `M${pts.join("L")}`;
  let d = `M${pts[0]}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const [x, y] = pts[i];
    const [nx, ny] = pts[i + 1];
    d += ` Q${x},${y} ${(x + nx) / 2},${(y + ny) / 2}`;
  }
  return `${d} L${pts[pts.length - 1]}`;
}

function renderTimeline(forecast, status) {
  const observed = state.observed;
  if (!observed.length) return;

  const horizon = forecast.horizon || [];
  const now = status.current_window;
  const { l, r, t, b } = PLOT;
  const xMin = (observed[0].window - now) * SEC_PER_WINDOW;
  const xMax = horizon.length * SEC_PER_WINDOW;
  const X = (s) => l + ((s - xMin) / Math.max(xMax - xMin, 1)) * (r - l);
  const Y = (p) => b - p * (b - t);

  const parts = [
    '<defs><linearGradient id="risk-fill" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0" stop-color="#ff4d00" stop-opacity="0.18"/>' +
      '<stop offset="1" stop-color="#ff4d00" stop-opacity="0"/></linearGradient></defs>',
    '<text x="14" y="16" class="c-axis">Risk(%)</text>',
    `<text x="${(l + r) / 2}" y="366" class="c-axis" text-anchor="middle">Time(s)</text>`,
    `<line x1="${l}" y1="${t - 5}" x2="${l}" y2="${b}" class="c-axis-line"/>`,
    `<line x1="${l}" y1="${b}" x2="${r}" y2="${b}" class="c-axis-line"/>`,
  ];

  for (let i = 0; i <= 4; i++) {
    const y = t + (i * (b - t)) / 4;
    parts.push(`<text x="36" y="${y + 4}" class="c-axis" text-anchor="end">${100 - i * 25}</text>`);
  }

  const step = niceStep(xMax - xMin);
  for (let s = Math.ceil(xMin / step) * step; s <= xMax; s += step) {
    parts.push(`<text x="${X(s)}" y="344" class="c-axis" text-anchor="middle">` +
      `${s > 0 ? "+" : ""}${s}</text>`);
  }

  const last = observed[observed.length - 1];
  const seen = observed.map((o) => [X((o.window - now) * SEC_PER_WINDOW), Y(o.probability)]);
  const ahead = [[X(0), Y(last.probability)]].concat(
    horizon.map((h, i) => [X((i + 1) * SEC_PER_WINDOW), Y(h.probability)])
  );

  const curve = smoothPath(seen);
  parts.push(`<path d="${curve} L${seen[seen.length - 1][0]},${b} L${seen[0][0]},${b} Z" fill="url(#risk-fill)"/>`);
  parts.push(`<path d="${curve}" class="c-line"/>`);
  parts.push(`<path d="${smoothPath(ahead)}" class="c-line c-line-forecast"/>`);

  const cx = X(0);
  const cy = Y(last.probability);
  parts.push(`<line x1="${cx}" y1="${t - 5}" x2="${cx}" y2="${b}" class="c-crosshair"/>`);
  parts.push(`<line x1="${l}" y1="${cy}" x2="${r}" y2="${cy}" class="c-crosshair"/>`);
  parts.push(`<circle cx="${cx}" cy="${cy}" r="4.5" class="c-dot">` +
    `<title>now: ${(last.probability * 100).toFixed(1)}%</title></circle>`);

  $("timeline-svg").innerHTML = parts.join("");
}
/* Progression rows: every tactic seen so far is complete except the current
   one, which carries the backend's confidence. The contract has no per-stage
   forecast, so no "predicted" rows are shown. */
function renderStage(stage) {
  $("stage-name").textContent = stage.tactic_name;
  $("stage-id").textContent = `(${stage.tactic_id})`;

  const trail = state.stageTrail;
  if (trail[trail.length - 1] !== stage.tactic_name) trail.push(stage.tactic_name);
  $("stage-trail").replaceChildren(...trail.map((name, i) => {
    const active = i === trail.length - 1;
    const li = document.createElement("li");
    li.className = `stage-row ${active ? "active" : "done"}`;
    const label = document.createElement("span");
    label.className = "stage-label";
    label.textContent = name;
    const status = document.createElement("span");
    status.className = "stage-status";
    status.textContent = active
      ? `${(stage.confidence * 100).toFixed(0)}% active`
      : "100% completed";
    li.append(label, status);
    return li;
  }));
}

// horizontal bar rows: [{name, value, display}] scaled to the largest |value|
function barRows(container, rows) {
  const max = Math.max(...rows.map((r) => Math.abs(r.value)), 1e-9);
  container.replaceChildren(...rows.map((r) => {
    const row = document.createElement("div");
    row.className = "bar-row";
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = r.name;
    name.title = r.name;
    const track = document.createElement("div");
    track.className = "bar-track";
    const fill = document.createElement("div");
    fill.className = "bar-fill";
    fill.style.width = `${(Math.abs(r.value) / max) * 100}%`;
    track.appendChild(fill);
    const val = document.createElement("span");
    val.className = "val";
    val.textContent = r.display;
    if (r.title) row.title = r.title;
    row.append(name, val, track); // label and value share the top row, bar below
    return row;
  }));
}

/* The bar and its label both show the feature's share of the strongest
   contribution; the signed value stays on the row's tooltip. */
const TOP_FEATURES = 4; // the 2x2 grid in the design

function renderExplanations(expl) {
  $("expl-summary").textContent = expl.summary;
  state.features = expl.top_features;
  drawFeatures();
}

function drawFeatures() {
  const all = state.features;
  if (!all.length) return;
  const max = Math.max(...all.map((f) => Math.abs(f.contribution)), 1e-9);
  const shown = state.allFeatures ? all : all.slice(0, TOP_FEATURES);
  barRows($("expl-features"), shown.map((f) => ({
    name: f.feature,
    value: f.contribution,
    display: `${Math.round((Math.abs(f.contribution) / max) * 100)}%`,
    title: `contribution ${f.contribution >= 0 ? "+" : ""}${f.contribution.toFixed(3)}`,
  })));
}

$("expl-toggle").addEventListener("click", (ev) => {
  state.allFeatures = !state.allFeatures;
  ev.target.textContent = state.allFeatures ? "Top factors only" : "View All factors";
  drawFeatures();
});
function fmtBytes(n) {
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)} GB`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(2)} MB`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)} KB`;
  return `${n} B`;
}

function renderFlagged(flows) {
  $("ff-count").textContent = flows.length;
  const body = $("ff-body");
  if (!flows.length) return;
  body.replaceChildren(...flows.slice().reverse().map((f) => {
    const tr = document.createElement("tr");
    const cells = [
      new Date(f.flow.start_time).toLocaleTimeString(),
      `${f.flow.src_ip}:${f.flow.src_port}`,
      `${f.flow.dst_ip}:${f.flow.dst_port}`,
      f.flow.protocol,
      String(f.flow.packet_count),
      f.score.toFixed(2),
      f.reason,
    ];
    tr.replaceChildren(...cells.map((text, i) => {
      const td = document.createElement("td");
      td.textContent = text;
      if (i === 4 || i === 5) td.className = "num";
      return td;
    }));
    return tr;
  }));
}

function renderTraffic(summary) {
  $("ts-windows").textContent = summary.window_count;
  $("ts-flows").textContent = summary.flow_count.toLocaleString();
  $("ts-packets").textContent = summary.packet_count.toLocaleString();
  $("ts-bytes").textContent = fmtBytes(summary.byte_count);

  const protos = Object.entries(summary.protocol_counts).sort((a, b) => b[1] - a[1]);
  barRows($("ts-protocols"), protos.map(([name, count]) => ({
    name, value: count, display: count.toLocaleString(),
  })));

  const ol = $("ts-talkers");
  ol.replaceChildren(...summary.top_talkers.map((ip) => {
    const li = document.createElement("li");
    li.textContent = ip;
    return li;
  }));
}

/* ---------- boot ---------- */

startPolling(); // attaches to the session the landing page just started
