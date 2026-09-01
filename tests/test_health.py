from fastapi.testclient import TestClient

from backend.app.main import app


def test_health():
    resp = TestClient(app).get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body
