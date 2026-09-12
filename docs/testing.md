# Testing strategy

Framework: **pytest** only. Run everything with `pytest` from the repo root.
Tests must run fully offline and finish in seconds — they are the gate for
every merge to `main`.

## Layers

### 1. Contract tests (`tests/test_contracts_*.py`) — Phase 1+

Validate that any implementation of a module entry point (mock **or** real)
returns valid `contracts/` types with sane values (probabilities in [0, 1],
windows ordered in time, non-empty feature names, ...). Written once against
the contract; module owners run the same tests against their real code
before integration — this is what makes mock→real swaps safe.

### 2. Backend API tests (`tests/test_api_*.py`) — Phase 2+

FastAPI `TestClient`, mocks active. Cover: session creation from a sample
CSV, status progression, every result endpoint's shape, and error paths
(no session yet, malformed/oversized upload, unsupported file type).
`tests/test_health.py` (Phase 0) is the template.

### 3. End-to-end replay run

One test: start a session on `data/samples/`, drive the replay to
completion, assert every endpoint returns coherent data for the final
window. This is the "demo will work" test.

### 4. Dashboard smoke test (`tests/test_dashboard.py`) — Phase 4+

Flask `test_client`: each page returns 200 and contains its panel sections.
No visual/JS testing — the dashboard is thin by design.

## What is deliberately not tested by me

Model quality, feature-extraction correctness, and MITRE mapping accuracy
are their module owners' responsibility (inside `modules/<name>/`). My tests
only enforce the contract boundary.

## Manual demo checklist (Phase 6, before judging)

1. Fresh clone → venv → `pip install -r requirements.txt` (offline wheel
   cache if no internet) → `pytest` green.
2. Start backend + dashboard, load a sample file, watch a full replay.
3. Verify the first five positions show warm-up rather than a fabricated
   probability, then verify real LSTM output after six windows.
4. Let a forecast alert appear, open the evidence panel, and click Verify.
4. Kill/restart the backend mid-replay — dashboard must degrade gracefully
   ("backend unreachable"), not crash.
