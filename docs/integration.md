# Integration guide (for module owners)

How the Data Pipeline, ML Forecasting and Attack Intelligence modules plug
into the application. Read this before writing module code.

## The model

- Your module is a **plain Python package** in `modules/<your_module>/`.
- The backend **imports it in-process** — no services, no ports, no Docker.
- The boundary between us is a **typed contract**: Pydantic models defined in
  `contracts/` plus one entry-point function per module (below).
- Until your module is ready, the backend runs a **mock** with the same
  signature (`backend/app/services/`), so backend/dashboard development never
  blocks on you — and you can develop/test against the same contract without
  running the app.

Rules:

- Only exchange types from `contracts/`. Never return raw DataFrames, dicts,
  or module-internal classes across the boundary.
- Contract changes are proposed to the tech lead and made in `contracts/`
  first, in their own commit — never by silently changing your return values.
- Everything must run offline: bundle model weights/lookup data inside your
  module directory (large binaries are gitignored — document how to
  regenerate or share them).
- Declare new Python dependencies by PR-ing `requirements.txt` (pinned).

## Module contracts

Exact Pydantic definitions live in `contracts/` (built in Phase 1; field
lists below are the agreed starting point and may be refined together).

### 1. Data Pipeline — `modules/data_pipeline`

```python
def process(input_path: Path, config: dict) -> list[NetworkState]
```

Reads a PCAP or CSV file, cleans it, extracts flow + packet-level features,
and splits traffic into time windows. `NetworkState` ≈ window start/end,
feature vector (named features), per-window flow records, basic counts.

### 2. ML Forecasting — `modules/forecasting`

```python
def forecast(states: list[NetworkState], config: dict) -> ForecastResult
```

Learns from past windows and predicts future attack risk.
`ForecastResult` ≈ current infiltration probability, per-future-step
probability timeline (the horizon), and model metadata.

### 3. Attack Intelligence — `modules/attack_intelligence`

```python
def analyze(states: list[NetworkState], forecast: ForecastResult,
            config: dict) -> IntelligenceResult
```

`IntelligenceResult` bundles: `AttackStagePrediction` (MITRE ATT&CK stage +
confidence), `Explanation` (top contributing features/reasons), and
`list[FlaggedFlow]` (suspicious flows with reasons).

`config` is the relevant section of `config.yaml` — put your tunables there.

## How your module gets swapped in

`backend/app/services/` selects the implementation: mock by default, your
real module once it exists (a one-line switch per module, controlled from
`config.yaml`). Swap order can be arbitrary — each module is replaced
independently.

## Verifying your module

1. `pip install -r requirements.txt` in the repo venv.
2. Run the contract tests: `pytest tests/` — they call your entry point on
   `data/samples/ssh_bruteforce_2018-02-14.csv` and validate the returned
   contract types.
3. Run the full app (README) and confirm the dashboard shows your real
   output instead of mock data.
