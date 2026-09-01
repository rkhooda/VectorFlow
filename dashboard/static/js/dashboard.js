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

function renderRisk() {}
function renderTimeline() {}
function renderStage() {}
function renderExplanations() {}
function renderFlagged() {}
function renderTraffic() {}

/* ---------- boot ---------- */

initControls();
startPolling(); // re-attaches to an in-progress session after a page reload
