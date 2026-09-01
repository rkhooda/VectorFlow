"""SIH26153 backend — FastAPI application entry point.

Run with: uvicorn backend.app.main:app --port 8000
"""

from fastapi import FastAPI

from backend.app.api import results, session
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
        return {"status": "ok", "version": APP_VERSION}

    app.include_router(session.router)
    app.include_router(results.router)

    return app


app = create_app()
