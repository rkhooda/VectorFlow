"""SIH26153 dashboard — Flask application entry point.

Run with: python dashboard/app.py

The browser talks only to Flask (same origin); Flask forwards /api/* to the
FastAPI backend through api_client, so no CORS setup is needed anywhere.
"""

import sys
from pathlib import Path

import yaml
from flask import Flask, abort, jsonify, render_template, request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard import api_client  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]

with open(REPO_ROOT / "config.yaml") as f:
    _cfg = yaml.safe_load(f)

app = Flask(__name__)

# GET paths the frontend may reach on the backend — the full result contract.
PROXY_GET_PATHS = {
    "/api/session/status",
    "/api/state/current",
    "/api/forecast",
    "/api/stage",
    "/api/explanations",
    "/api/flows/flagged",
    "/api/traffic/summary",
}


def list_samples() -> list[str]:
    samples_dir = REPO_ROOT / _cfg["data"]["samples_dir"]
    allowed = set(_cfg["session"]["allowed_extensions"])
    if not samples_dir.is_dir():
        return []
    return sorted(p.name for p in samples_dir.iterdir() if p.suffix.lower() in allowed)


@app.route("/")
def index():
    return render_template("index.html", samples=list_samples())


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", backend=api_client.backend_health())


@app.route("/api/<path:path>")
def proxy_get(path):
    full = f"/api/{path}"
    if full not in PROXY_GET_PATHS:
        abort(404)
    body, status = api_client.proxy_get(full)
    return jsonify(body), status


@app.route("/api/session", methods=["POST"])
def start_session():
    upload = request.files.get("file")
    body, status = api_client.start_session(
        sample=request.form.get("sample") or None,
        upload=upload if upload and upload.filename else None,
    )
    return jsonify(body), status


if __name__ == "__main__":
    dash = _cfg["dashboard"]
    app.run(host=dash["host"], port=dash["port"], debug=True)
