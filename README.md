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

For a machine without internet, build a wheel cache once where you have it
(about 52 MB) and install from that:

```bash
pip download -r requirements.txt -d wheels/
pip install --no-index --find-links wheels -r requirements.txt
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

## Demo

Pick `ssh_bruteforce_2018-02-14.csv` on the home page. It is a 13-minute slice
of the CIC-IDS-2018 Feb 14 capture: 75 ten-second windows, replayed at two
seconds each (about 2.5 minutes).

- Windows 1–26 are benign. Risk stays low with one brief bump around window
  13; the stage sits at Reconnaissance or Initial Access.
- Window 27 (02:01:50) is where the SSH brute force starts. Flows roughly
  triple, risk climbs above 65% and stays there, and the stage moves through
  Initial Access and Lateral Movement to Exfiltration.
- Flagged flows, protocol breakdown and top talkers stay empty: CIC-IDS-2018
  day files carry no IPs or ports, so per-flow records cannot be rebuilt.

The data pipeline and attack intelligence are the real modules. The risk
number comes from an activity baseline (`mock-forecaster-v0`) until the
trained model beats chance on the March test days; the swap is one line in
`config.yaml`.

Uploading a CSV that is not a CIC-IDS-2018 flow export puts the session in
the error state with the missing columns named. PCAP must be converted with
CICFlowMeter first.

## Tests

```bash
pytest
```

## Documentation

Start with `docs/implementation-plan.md` and `docs/architecture.md`.
Module owners: read `docs/integration.md` for the contract your module must
implement.
