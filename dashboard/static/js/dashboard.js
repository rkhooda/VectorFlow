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

/* ---------- session start ---------- */

function initControls() {
  $("session-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const form = ev.target;
    const data = new FormData();
    const file = $("file-input").files[0];
    const sample = $("sample-select").value;
    if (file) data.append("file", file);
    else if (sample) data.append("sample", sample);
    else { $("controls-msg").textContent = "Choose a sample or upload a file first."; return; }

    $("start-btn").disabled = true;
    $("controls-msg").textContent = "Starting analysis…";
    const resp = await api("/api/session", { method: "POST", body: data });
    $("start-btn").disabled = false;

    if (!resp.ok) {
      const detail = (resp.body && resp.body.detail) || "backend not reachable";
      $("controls-msg").textContent = `Could not start session: ${detail}`;
      return;
    }
    clearError();
    resetPanels();
    $("controls-msg").textContent = `Session ${resp.body.session_id} started.`;
    form.reset();
    startPolling();
  });
}

function resetPanels() {
  state.observed = [];
  state.stageTrail = [];
  state.lastWindow = 0;
  state.finished = false;
}

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
    $("ns-detail").textContent = "Start an analysis to begin.";
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
function renderStage() {}
function renderExplanations() {}
function renderFlagged() {}
function renderTraffic() {}

/* ---------- boot ---------- */

initControls();
startPolling(); // re-attaches to an in-progress session after a page reload
