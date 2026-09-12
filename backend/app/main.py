"""SIH26153 backend — FastAPI application entry point.

Run with: uvicorn backend.app.main:app --port 8000
"""

from fastapi import FastAPI

from backend.app.api import evidence, results, session
from backend.app.services.blockchain_service import get_ledger
from backend.app.core.config import get_config

APP_VERSION = "0.1.0"


def create_app() -> FastAPI:
    app = FastAPI(
        title="SIH26153 Attack Forecasting API",
        version=APP_VERSION,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    @app.get("/api/health")
    def health() -> dict:
        get_config()  # fail fast if config.yaml is missing or invalid
        cfg = get_config()
        model_cfg = cfg.get("modules", {}).get("forecasting", {})
        try:
            from modules.forecasting import _pipeline

            _pipeline(model_cfg.get("artifacts_dir")).load_artifacts()
            model_status = "loaded"
        except (FileNotFoundError, ImportError, OSError, RuntimeError, ValueError):
            model_status = "missing"
        blockchain = cfg.get("blockchain", {})
        if not blockchain.get("enabled", True):
            ledger_status = "disabled"
        else:
            try:
                get_ledger(blockchain)._read()
                ledger_status = "connected"
            except (OSError, ValueError, TypeError):
                ledger_status = "offline"
        return {
            "status": "ok",
            "version": APP_VERSION,
            "model": model_status,
            "model_mode": model_cfg.get("implementation", "mock"),
            "blockchain": ledger_status,
            "replay": "stopped",
        }

    app.include_router(session.router)
    app.include_router(results.router)
    app.include_router(evidence.router)

    return app


app = create_app()
