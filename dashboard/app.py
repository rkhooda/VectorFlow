"""SIH26153 dashboard — Flask application entry point.

Run with: python dashboard/app.py
"""

import sys
from pathlib import Path

from flask import Flask, render_template

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard import api_client  # noqa: E402
import yaml  # noqa: E402

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html", backend=api_client.backend_health())


if __name__ == "__main__":
    with open(Path(__file__).resolve().parents[1] / "config.yaml") as f:
        cfg = yaml.safe_load(f)["dashboard"]
    app.run(host=cfg["host"], port=cfg["port"], debug=True)
