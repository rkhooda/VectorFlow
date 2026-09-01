from fastapi.testclient import TestClient
import pytest

from backend.app.core import store
from backend.app.core.config import get_config
from backend.app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_store():
    store.current = None


def test_status_without_session():
    assert client.get("/api/session/status").status_code == 404


def test_create_from_sample():
    resp = client.post("/api/session", data={"sample": "sample_flows.csv"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "replaying"
    assert body["current_window"] == 1
    assert body["input_file"] == "sample_flows.csv"
    assert body["total_windows"] == get_config()["modules"]["mock_windows"]
    assert client.get("/api/session/status").json()["session_id"] == body["session_id"]


def test_create_from_upload(tmp_path):
    resp = client.post(
        "/api/session",
        files={"file": ("capture.csv", b"timestamp,src_ip\n1,10.0.0.1\n", "text/csv")},
    )
    assert resp.status_code == 200
    assert resp.json()["state"] == "replaying"


def test_rejects_unsupported_extension():
    resp = client.post("/api/session", files={"file": ("notes.txt", b"hi", "text/plain")})
    assert resp.status_code == 400


def test_rejects_oversized_upload():
    max_mb = get_config()["session"]["max_upload_mb"]
    payload = b"x" * (max_mb * 1024 * 1024 + 1)
    resp = client.post("/api/session", files={"file": ("big.csv", payload, "text/csv")})
    assert resp.status_code == 413


def test_rejects_neither_and_both():
    assert client.post("/api/session").status_code == 400
    resp = client.post(
        "/api/session",
        data={"sample": "sample_flows.csv"},
        files={"file": ("a.csv", b"x", "text/csv")},
    )
    assert resp.status_code == 400


def test_sample_path_traversal_is_stripped():
    resp = client.post("/api/session", data={"sample": "../../etc/passwd"})
    assert resp.status_code == 404
    assert "passwd" in resp.json()["detail"]
    assert "../" not in resp.json()["detail"]
