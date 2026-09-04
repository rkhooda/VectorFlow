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

/* Single-hue line chart: observed windows (solid) + forecast horizon (dashed).
   Native <title> tooltips on the points; recessive gridlines. */
function renderTimeline(forecast, status) {
  const svg = $("timeline-svg");
  const observed = state.observed;
  if (!observed.length) return;

  const horizon = forecast.horizon || [];
  const lastX = status.total_windows + horizon.length;
  const W = 720, H = 200, PAD_L = 34, PAD_R = 8, PAD_T = 10, PAD_B = 22;
  const x = (w) => PAD_L + ((w - 1) / Math.max(lastX - 1, 1)) * (W - PAD_L - PAD_R);
  const y = (p) => PAD_T + (1 - p) * (H - PAD_T - PAD_B);

  const parts = [];
  // gridlines + y labels at 0 / 0.5 / 1
  for (const g of [0, 0.5, 1]) {
    parts.push(`<line x1="${PAD_L}" y1="${y(g)}" x2="${W - PAD_R}" y2="${y(g)}" stroke="#e5e7eb"/>`);
    parts.push(`<text x="${PAD_L - 6}" y="${y(g) + 4}" text-anchor="end" font-size="10" fill="#888">${g * 100}%</text>`);
  }
  // "now" marker at the current window
  const nowX = x(status.current_window);
  parts.push(`<line x1="${nowX}" y1="${PAD_T}" x2="${nowX}" y2="${H - PAD_B}" stroke="#bbb" stroke-dasharray="2 3"/>`);
  parts.push(`<text x="${nowX + 4}" y="${PAD_T + 10}" font-size="10" fill="#888">now</text>`);
  parts.push(`<text x="${PAD_L}" y="${H - 6}" font-size="10" fill="#888">window 1</text>`);
  parts.push(`<text x="${W - PAD_R}" y="${H - 6}" text-anchor="end" font-size="10" fill="#888">+${horizon.length} forecast</text>`);

  const pts = observed.map((o) => `${x(o.window)},${y(o.probability)}`);
  parts.push(`<polyline points="${pts.join(" ")}" fill="none" stroke="#3b6ff0" stroke-width="2"/>`);

  const last = observed[observed.length - 1];
  const fpts = [`${x(last.window)},${y(last.probability)}`].concat(
    horizon.map((h, i) => `${x(last.window + i + 1)},${y(h.probability)}`)
  );
  parts.push(`<polyline points="${fpts.join(" ")}" fill="none" stroke="#3b6ff0" stroke-width="2" stroke-dasharray="5 4" opacity="0.7"/>`);

  for (const o of observed) {
    parts.push(`<circle cx="${x(o.window)}" cy="${y(o.probability)}" r="3" fill="#3b6ff0">` +
      `<title>window ${o.window}: ${(o.probability * 100).toFixed(1)}%</title></circle>`);
  }
  horizon.forEach((h, i) => {
    parts.push(`<circle cx="${x(last.window + i + 1)}" cy="${y(h.probability)}" r="3" fill="#fff" stroke="#3b6ff0" stroke-width="1.5">` +
      `<title>forecast +${h.step}: ${(h.probability * 100).toFixed(1)}%</title></circle>`);
  });

  svg.innerHTML = parts.join("");
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
    row.append(name, track, val);
    return row;
  }));
}

function renderExplanations(expl) {
  $("expl-summary").textContent = expl.summary;
  barRows($("expl-features"), expl.top_features.map((f) => ({
    name: f.feature,
    value: f.contribution,
    display: (f.contribution >= 0 ? "+" : "") + f.contribution.toFixed(3),
  })));
}
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
