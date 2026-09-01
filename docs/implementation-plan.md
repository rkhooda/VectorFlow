# Implementation plan — Backend, Frontend & Integration

Scope: the Tech Lead's responsibilities (backend, dashboard, integration,
application structure) for SIH26153. Teammate modules (Data Pipeline, ML
Forecasting, Attack Intelligence) are developed independently against the
contracts in `contracts/` (see `docs/integration.md`).

## Dependency overview

| Work | Can start | Waits for |
|------|-----------|-----------|
| Phases 0–4 (contracts, mocks, full backend, full dashboard) | **immediately** | nothing — mocks stand in for every teammate module |
| Swap in real Data Pipeline | when their `process()` passes contract tests | Data Pipeline teammate |
| Swap in real Forecasting | when their `forecast()` passes contract tests | ML Forecasting teammate |
| Swap in real Attack Intelligence | when their `analyze()` passes contract tests | Attack Intelligence teammate |
| Real visual design | when the UI/UX designer delivers | designer |

Swaps are independent — integration is progressive, in whatever order
modules become ready (Phase 5). Until Attack Intelligence lands, the stage/
explanation panels show clearly-labelled mock data; same for the other
panels and their modules.

---

## Phase 0 — Repository foundation & scaffolds ✅ (done)

- **Objective**: clean, offline-runnable project skeleton the whole team
  builds on.
- **Built**: git repo, `.gitignore`, structure, pinned `requirements.txt`,
  `config.yaml`, FastAPI app with `/api/health`, Flask dashboard placeholder
  page showing backend health, docs, health smoke test.
- **Files**: repo root, `backend/`, `dashboard/`, `docs/`, `tests/test_health.py`.
- **Dependencies**: none.
- **Tested**: `pytest` green; both apps started; dashboard rendered
  "Backend status: ok (v0.1.0)".
- **Done when**: fresh clone + README steps work end to end. ✅

## Phase 1 — Contracts & mock modules

- **Objective**: freeze the team's data interfaces so all five people can
  work in parallel.
- **Build**: Pydantic models in `contracts/`: `NetworkState`, `FlowRecord`,
  `ForecastResult`, `AttackStagePrediction`, `Explanation`,
  `FlaggedFlow`, `TrafficSummary`, `IntelligenceResult`, `SessionStatus`.
  Mock implementations of all three module entry points
  (`backend/app/services/mocks.py`) returning realistic, replay-varying
  fake data. Contract tests.
- **Files**: `contracts/*.py`, `backend/app/services/mocks.py`,
  `tests/test_contracts_*.py`.
- **Dependencies**: none (share drafts with teammates for review).
- **Output**: importable `contracts` package; mocks passing contract tests.
- **Tested**: contract tests validate types and value ranges for all mocks.
- **Done when**: teammates have reviewed/accepted the contracts and
  `pytest` is green.

## Phase 2 — Ingest & session API

- **Objective**: get a PCAP/CSV into the system and run the pipeline once.
- **Build**: `POST /api/session` (multipart upload with size/type
  validation, or sample-file name), `GET /api/session/status`, in-memory
  session store, orchestrator in `backend/app/core/` calling
  process → forecast → analyze (mocks), small sample CSV in `data/samples/`.
- **Files**: `backend/app/api/session.py`, `backend/app/core/orchestrator.py`,
  `backend/app/core/store.py`, `data/samples/sample_flows.csv`.
- **Dependencies**: Phase 1 only. (Ask Data Pipeline teammate for a
  realistic sample CSV; a hand-made one works meanwhile.)
- **Output**: a session can be created and reaches status `completed`.
- **Tested**: API tests — happy path, invalid file, oversized file, no
  session.
- **Done when**: `curl -F file=@sample.csv /api/session` then polling
  status shows completion; tests green.

## Phase 3 — Replay engine & result APIs

- **Objective**: everything the dashboard needs, evolving over time like a
  live capture.
- **Build**: replay loop (background task advancing one window per
  `replay.seconds_per_window`), and `GET /api/state/current`, `/api/forecast`,
  `/api/stage`, `/api/explanations`, `/api/flows/flagged`,
  `/api/traffic/summary` — each answering as of the current replay position.
- **Files**: `backend/app/core/replay.py`, `backend/app/api/results.py`.
- **Dependencies**: Phase 2.
- **Output**: full API surface of `docs/backend.md` live on mock data.
- **Tested**: e2e mock run test; per-endpoint API tests.
- **Done when**: watching `/api/forecast` during replay shows the
  probability timeline advancing; tests green.

## Phase 4 — Dashboard pages

- **Objective**: judges can see every PS-required panel update live.
- **Build**: upload/sample-select form; JS polling (`static/js/`) filling
  the eight panels of `docs/frontend.md` (replay status, network state,
  probability, forecast timeline, MITRE stage, explanations, flagged flows,
  traffic summary). Structural markup only — restyled when the designer
  delivers.
- **Files**: `dashboard/app.py`, `dashboard/templates/*`,
  `dashboard/static/js/*`.
- **Dependencies**: Phases 2–3. Visual design NOT required to start.
- **Output**: complete working demo on mock data.
- **Tested**: dashboard smoke tests + manual replay walkthrough.
- **Done when**: full upload→replay→panels demo works with only mocks.

## Phase 5 — Progressive module integration

- **Objective**: replace mocks with real teammate modules, one at a time.
- **Build**: per module — implementation switch in
  `backend/app/services/` (driven by `config.yaml`), run contract tests
  against the real module, fix contract mismatches together, verify in the
  dashboard. Expected order: data_pipeline → forecasting →
  attack_intelligence, but any order works.
- **Files**: `backend/app/services/__init__.py`, `config.yaml`,
  `modules/<name>/` (theirs).
- **Dependencies**: each teammate's delivered module.
- **Output**: dashboard shows real analysis instead of mock data.
- **Tested**: same contract + e2e tests, now against real modules.
- **Done when**: all three switches point at real modules and everything
  is green.

## Phase 6 — Hardening & demo preparation

- **Objective**: survive the judging room.
- **Build**: graceful degradation (backend down, empty/odd input files),
  offline install path (local wheel cache), README/docs final pass, demo
  script + `data/samples/` scenario that shows a convincing attack
  progression, apply the designer's UI.
- **Dependencies**: Phases 4–5 (UI design can land any time).
- **Tested**: manual demo checklist in `docs/testing.md` on a fresh clone
  with networking disabled.
- **Done when**: a teammate can run the full demo from the README alone,
  offline, first try.
