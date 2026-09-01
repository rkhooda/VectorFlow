"""Thin HTTP client for the FastAPI backend (localhost only)."""

import requests
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

with open(REPO_ROOT / "config.yaml") as f:
    _cfg = yaml.safe_load(f)["backend"]

BASE_URL = f"http://{_cfg['host']}:{_cfg['port']}"

UNREACHABLE = {"detail": "backend unreachable"}


def get(path: str) -> dict:
    """GET an /api/* path; raises requests.RequestException if backend is down."""
    resp = requests.get(f"{BASE_URL}{path}", timeout=5)
    resp.raise_for_status()
    return resp.json()


def backend_health() -> dict:
    try:
        return get("/api/health")
    except requests.RequestException:
        return {"status": "unreachable"}


def proxy_get(path: str) -> tuple[dict, int]:
    """GET a backend path, passing body and status code through (404/409 included)."""
    try:
        resp = requests.get(f"{BASE_URL}{path}", timeout=5)
        return resp.json(), resp.status_code
    except (requests.RequestException, ValueError):
        return UNREACHABLE, 502


def start_session(sample: str | None = None, upload=None) -> tuple[dict, int]:
    """POST /api/session with either a sample name or an uploaded file object."""
    try:
        if upload is not None:
            resp = requests.post(
                f"{BASE_URL}/api/session",
                files={"file": (upload.filename, upload.stream, upload.mimetype)},
                timeout=30,
            )
        else:
            resp = requests.post(
                f"{BASE_URL}/api/session", data={"sample": sample}, timeout=30
            )
        return resp.json(), resp.status_code
    except (requests.RequestException, ValueError):
        return UNREACHABLE, 502
