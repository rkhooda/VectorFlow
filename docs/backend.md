# Backend (FastAPI)

Entry point: `backend/app/main.py` (`create_app()` factory).
Run: `uvicorn backend.app.main:app --port 8000`.
Interactive API docs (offline): `http://127.0.0.1:8000/api/docs`.

## Layout

```
backend/app/
├── main.py        # app factory, router registration
├── api/           # one router per concern (session, results, ...)
├── core/          # config.py (loads config.yaml), orchestrator (Phase 2+)
└── services/      # module adapters, mocks, and local evidence ledger
```

## Session & replay model

One analysis session at a time (single-user prototype):

1. `POST /api/session` — process an uploaded PCAP/CSV or a sample file and
   prepare replay states. Forecasts are not precomputed.
2. The **replay engine** advances a simulated clock one time window per
   `replay.seconds_per_window` seconds (`config.yaml`). Each newly visible
   position runs the canonical model on its historical prefix exactly once.
3. The dashboard polls the result endpoints below; each returns the state as
   of the current replay position.

Session state is held in memory (a module-level store). Restarting the
backend clears it — acceptable for the prototype.

## API surface

| Method | Path                    | Returns |
|--------|-------------------------|---------|
| GET    | `/api/health`           | `{status, version}` — implemented (Phase 0) |
| POST   | `/api/session`          | start analysis: file upload or sample name; returns session id/status |
| GET    | `/api/session/status`   | input/replay status, progress, current window index |
| GET    | `/api/state/current`    | current `NetworkState` (window features, basic traffic info) |
| GET    | `/api/forecast`         | `ForecastResult`: infiltration probability + horizon timeline |
| GET    | `/api/stage`            | `AttackStagePrediction`: predicted MITRE ATT&CK stage + confidence |
| GET    | `/api/explanations`     | `Explanation`: top contributing features / reasons |
| GET    | `/api/flows/flagged`    | list of `FlaggedFlow` (suspicious flows with reasons) |
| GET    | `/api/traffic/summary`  | `TrafficSummary`: counts, protocols, top talkers |
| GET    | `/api/alerts`            | deduplicated forecast alerts |
| GET    | `/api/evidence`          | evidence records and ledger status |
| GET    | `/api/evidence/{id}/verify` | recalculated hash and chain verification |

Response shapes are exactly the Pydantic models in `contracts/` — FastAPI
serializes them directly, so the contract and the API can never drift apart.

## Configuration

`backend/app/core/config.py` loads `config.yaml` from the repo root
(cached with `lru_cache`). Add new settings there, never as hardcoded
constants or environment variables.
