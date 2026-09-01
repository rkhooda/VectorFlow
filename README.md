# SIH26153 — AI-based Network Attack Forecasting from Network Traffic Data

Fully offline prototype that analyzes network traffic (PCAP/CSV), builds
time-based network states, forecasts future attack probability with an AI
world model, maps the predicted attack to a MITRE ATT&CK stage, and explains
the driving features — all shown on a dashboard.

```
Network traffic (PCAP/CSV)
  → feature extraction / preprocessing   (Data Pipeline)
  → time-based network states
  → AI forecasting / world model         (ML Forecasting)
  → future attack probability
  → predicted attack stage + reasons     (Attack Intelligence)
  → dashboard                            (Backend + Frontend)
```

## Repository layout

| Path         | What it is |
|--------------|------------|
| `contracts/` | Pydantic data models shared by every module — the team's interface contract |
| `modules/`   | Team modules: `data_pipeline/`, `forecasting/`, `attack_intelligence/` |
| `backend/`   | FastAPI application: session/replay orchestration, JSON API at `/api/*` |
| `dashboard/` | Flask web dashboard for judges (calls the backend over localhost) |
| `data/`      | Sample input files (`samples/`) and runtime uploads (`uploads/`, untracked) |
| `tests/`     | pytest suite |
| `docs/`      | Architecture, implementation plan, integration and testing docs |

## Setup (offline, reproducible)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

Two processes, two terminals:

```bash
# 1. Backend API  → http://127.0.0.1:8000/api/health
uvicorn backend.app.main:app --port 8000

# 2. Dashboard    → http://127.0.0.1:5000/
python dashboard/app.py
```

Configuration lives in `config.yaml`. No internet access is required at any
point.

## Tests

```bash
pytest
```

## Documentation

Start with `docs/implementation-plan.md` and `docs/architecture.md`.
Module owners: read `docs/integration.md` for the contract your module must
implement.
