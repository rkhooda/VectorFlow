import time

import pytest
from fastapi.testclient import TestClient

from backend.app.core import store
from backend.app.core.config import get_config
from backend.app.main import app
from contracts import SessionState

client = TestClient(app)
SPW = get_config()["replay"]["seconds_per_window"]
ENDPOINTS = [
    "/api/state/current",
    "/api/forecast",
    "/api/stage",
    "/api/explanations",
    "/api/flows/flagged",
    "/api/traffic/summary",
]


@pytest.fixture(autouse=True)
def fresh_store():
    store.current = None


def start_session():
    assert client.post("/api/session", data={"sample": "sample_flows.csv"}).status_code == 200


def set_position(windows_seen: int):
    """Rewind the replay clock so exactly `windows_seen` windows have played."""
    store.current.replay_started = time.monotonic() - SPW * (windows_seen - 1) - 0.01


def test_all_endpoints_404_without_session():
    for ep in ENDPOINTS:
        assert client.get(ep).status_code == 404, ep


def test_all_endpoints_409_when_session_errored():
    start_session()
    store.current.status.state = SessionState.error
    for ep in ENDPOINTS:
        assert client.get(ep).status_code == 409, ep


def test_replay_position_is_consistent_across_endpoints():
    start_session()
    set_position(3)
    status = client.get("/api/session/status").json()
    assert status["state"] == "replaying"
    assert status["current_window"] == 3
    assert client.get("/api/state/current").json()["window_index"] == 2
    summary = client.get("/api/traffic/summary").json()
    assert summary["window_count"] == 3
    seen = store.current.states[:3]
    assert summary["flow_count"] == sum(s.flow_count for s in seen)
    assert summary["byte_count"] == sum(s.byte_count for s in seen)
    assert 1 <= len(summary["top_talkers"]) <= 5
    expected_flagged = sum(len(i.flagged_flows) for i in store.current.intelligence[:3])
    assert len(client.get("/api/flows/flagged").json()) == expected_flagged


def test_result_shapes_mid_replay():
    start_session()
    set_position(5)
    forecast = client.get("/api/forecast").json()
    assert 0.0 <= forecast["infiltration_probability"] <= 1.0
    assert [p["step"] for p in forecast["horizon"]] == list(range(1, len(forecast["horizon"]) + 1))
    stage = client.get("/api/stage").json()
    assert stage["tactic_id"].startswith("TA")
    explanation = client.get("/api/explanations").json()
    assert explanation["top_features"] and explanation["summary"]


def test_forecast_escalates_as_replay_advances():
    start_session()
    set_position(2)
    early = client.get("/api/forecast").json()["infiltration_probability"]
    set_position(20)
    late = client.get("/api/forecast").json()["infiltration_probability"]
    assert late > early


def test_replay_completes():
    start_session()
    set_position(10_000)
    status = client.get("/api/session/status").json()
    assert status["state"] == "completed"
    assert status["current_window"] == status["total_windows"]
    # result endpoints still answer at the final window after completion
    assert client.get("/api/state/current").json()["window_index"] == status["total_windows"] - 1
