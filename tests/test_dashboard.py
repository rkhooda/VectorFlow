"""Dashboard (Flask) tests: page rendering, backend proxy, error handling."""

import pytest
from fastapi.testclient import TestClient

import dashboard.app as dashboard_app
from backend.app.core import store
from backend.app.main import app as fastapi_app

client = dashboard_app.app.test_client()

PANEL_IDS = [
    "network-status",
    "attack-risk",
    "forecast-timeline",
    "attack-stage",
    "explanations",
    "flagged-flows",
    "traffic-summary",
]


@pytest.fixture
def backend_up(monkeypatch):
    """Wire the Flask proxy to the real FastAPI app in-process."""
    tc = TestClient(fastapi_app)
    store.current = None

    def proxy_get(path):
        resp = tc.get(path)
        return resp.json(), resp.status_code

    def start_session(sample=None, upload=None):
        if upload is not None:
            resp = tc.post(
                "/api/session",
                files={"file": (upload.filename, upload.stream, upload.mimetype)},
            )
        else:
            resp = tc.post("/api/session", data={"sample": sample})
        return resp.json(), resp.status_code

    monkeypatch.setattr(dashboard_app.api_client, "proxy_get", proxy_get)
    monkeypatch.setattr(dashboard_app.api_client, "start_session", start_session)
    yield
    store.current = None


def test_index_shows_upload_form():
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="session-form"' in html
    assert "ssh_bruteforce_2018-02-14.csv" in html  # sample selector is populated
    assert 'href="/dashboard"' in html


def test_dashboard_loads_with_all_panels(monkeypatch):
    monkeypatch.setattr(
        dashboard_app.api_client,
        "backend_health",
        lambda: {"status": "ok", "version": "0.1.0"},
    )
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    for panel in PANEL_IDS:
        assert f'id="{panel}"' in html
    assert "backend: ok" in html


def test_dashboard_survives_backend_down(monkeypatch):
    monkeypatch.setattr(
        dashboard_app.api_client, "backend_health", lambda: {"status": "unreachable"}
    )
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "backend: unreachable" in resp.get_data(as_text=True)


def test_proxy_rejects_unknown_paths():
    assert client.get("/api/does/not/exist").status_code == 404


def test_proxy_returns_502_when_backend_down(monkeypatch):
    monkeypatch.setattr(
        dashboard_app.api_client,
        "proxy_get",
        lambda path: ({"detail": "backend unreachable"}, 502),
    )
    resp = client.get("/api/session/status")
    assert resp.status_code == 502
    assert resp.get_json()["detail"] == "backend unreachable"


def test_status_404_passes_through_before_session(backend_up):
    resp = client.get("/api/session/status")
    assert resp.status_code == 404


def test_results_409_passes_through_when_not_ready(backend_up, monkeypatch):
    from contracts import SessionState, SessionStatus

    store.current = store.Session(
        status=SessionStatus(session_id="x", state=SessionState.processing)
    )
    assert client.get("/api/forecast").status_code == 409


def test_full_session_flow_through_dashboard(backend_up):
    # start a session through the dashboard proxy
    resp = client.post("/api/session", data={"sample": "ssh_bruteforce_2018-02-14.csv"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["state"] == "replaying"
    assert body["total_windows"] > 0

    # replay status is visible
    status = client.get("/api/session/status").get_json()
    assert status["state"] in ("replaying", "completed")
    assert status["current_window"] >= 1

    # every result panel endpoint answers with contract-shaped data
    forecast = client.get("/api/forecast").get_json()
    assert 0.0 <= forecast["infiltration_probability"] <= 1.0
    assert forecast["horizon"]

    stage = client.get("/api/stage").get_json()
    assert stage["tactic_id"] and stage["tactic_name"]

    expl = client.get("/api/explanations").get_json()
    assert expl["summary"] and expl["top_features"]

    assert client.get("/api/flows/flagged").status_code == 200

    traffic = client.get("/api/traffic/summary").get_json()
    assert traffic["window_count"] >= 1
    assert isinstance(traffic["protocol_counts"], dict)  # empty: CIC flows carry no protocol

    netstate = client.get("/api/state/current").get_json()
    assert netstate["window_index"] >= 0


def test_start_session_requires_input(backend_up):
    # no sample and no file → backend 400 passes through
    resp = client.post("/api/session", data={})
    assert resp.status_code == 400
