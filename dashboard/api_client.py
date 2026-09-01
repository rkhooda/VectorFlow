"""Thin HTTP client for the FastAPI backend (localhost only)."""

import requests
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

with open(REPO_ROOT / "config.yaml") as f:
    _cfg = yaml.safe_load(f)["backend"]

BASE_URL = f"http://{_cfg['host']}:{_cfg['port']}"


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
