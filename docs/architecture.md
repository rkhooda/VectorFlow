# Architecture

SIH26153 — AI-based Network Attack Forecasting from Network Traffic Data.
Fully offline prototype. Team system design: `sih26153-system-design.excalidraw`
(repo root).

## Topology

Two local processes, both from one repo, one venv, one `config.yaml`:

```
┌───────────────────┐        HTTP (localhost)        ┌─────────────────────────────┐
│  Flask dashboard  │ ─────────────────────────────▶ │  FastAPI backend  /api/*    │
│  dashboard/       │   polls JSON result endpoints  │  backend/                   │
│  :5000            │                                │  :8000                      │
└───────────────────┘                                └──────────────┬──────────────┘
                                                          in-process Python imports
                                                     ┌──────────────┴──────────────┐
                                                     │  modules/ (teammates' code) │
                                                     │  · data_pipeline            │
                                                     │  · forecasting              │
                                                     │  · attack_intelligence      │
                                                     └─────────────────────────────┘
```

- The **backend** owns orchestration: it accepts input, drives the analysis
  pipeline, holds session state in memory, and exposes results as JSON.
- The **dashboard** is a thin Flask app for judges: it renders pages and polls
  the backend via `dashboard/api_client.py`. It contains no analysis logic.
- **Team modules** are plain Python packages imported in-process by the
  backend. No microservices, no message queues, no database — a deliberate
  choice for an offline prototype (see `docs/integration.md`).

## Data flow

```
PCAP/CSV file (upload or data/samples/)
   │  POST /api/session
   ▼
backend orchestrator
   │  data_pipeline.process(raw)            → list[NetworkState]   (time windows)
   │  forecasting.forecast(states)          → ForecastResult       (probability + horizon)
   │  attack_intelligence.analyze(...)      → AttackStagePrediction, Explanation, FlaggedFlows
   ▼
replay engine (simulated clock advances one time window at a time)
   │  results per window stored in the in-memory session store
   ▼
JSON API  (/api/state/current, /api/forecast, /api/stage, /api/explanations,
           /api/flows/flagged, /api/traffic/summary, /api/session/status)
   ▼
Flask dashboard polls and renders: replay status, current state, attack
probability, forecast timeline, predicted MITRE ATT&CK stage, contributing
features, flagged flows, traffic summary
```

Shared data shapes live in `contracts/` (Pydantic models) — the single
source of truth for every module boundary.

## Offline constraints

- No network calls to anything except `localhost` (dashboard → backend).
- All dependencies pinned in `requirements.txt`; installable from a local
  wheel cache if needed (`pip download -r requirements.txt -d wheels/`).
- No CDN assets: any CSS/JS the dashboard needs is vendored in
  `dashboard/static/`.
- Reproducible configuration in `config.yaml`; no environment-dependent state.

## Out of scope (deliberately)

Authentication, databases, cloud services, LLM APIs, Docker/Kubernetes,
microservices. None are required by the problem statement.
