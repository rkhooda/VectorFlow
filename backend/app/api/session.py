"""Session ingest API: start an analysis from an upload or a sample file."""

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.app.core import orchestrator, replay, store
from backend.app.core.config import REPO_ROOT, get_config
from contracts import SessionState, SessionStatus

router = APIRouter(prefix="/api/session", tags=["session"])


@router.post("", response_model=SessionStatus)
async def create_session(
    file: UploadFile | None = File(default=None),
    sample: str | None = Form(default=None),
) -> SessionStatus:
    """Start an analysis from an uploaded PCAP/CSV or a named sample file."""
    cfg = get_config()
    if (file is None) == (sample is None):
        raise HTTPException(400, "provide exactly one of: file upload, sample name")

    if file is not None:
        allowed = set(cfg["session"]["allowed_extensions"])
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in allowed:
            raise HTTPException(400, f"unsupported file type '{suffix}'; allowed: {sorted(allowed)}")
        contents = await file.read()
        max_bytes = cfg["session"]["max_upload_mb"] * 1024 * 1024
        if len(contents) > max_bytes:
            raise HTTPException(413, f"file exceeds {cfg['session']['max_upload_mb']} MB limit")
        uploads_dir = REPO_ROOT / cfg["data"]["uploads_dir"]
        uploads_dir.mkdir(parents=True, exist_ok=True)
        input_path = uploads_dir / Path(file.filename).name  # strip any path components
        input_path.write_bytes(contents)
    else:
        # Path(...).name strips directory components → no path traversal
        input_path = REPO_ROOT / cfg["data"]["samples_dir"] / Path(sample).name
        if not input_path.is_file():
            raise HTTPException(404, f"sample '{Path(sample).name}' not found")

    session = orchestrator.run(input_path, cfg.get("modules", {}))
    return session.status


@router.get("/status", response_model=SessionStatus)
def session_status() -> SessionStatus:
    if store.current is None:
        raise HTTPException(404, "no session yet — POST /api/session first")
    if store.current.status.state in (SessionState.replaying, SessionState.completed):
        replay.advance(store.current, get_config()["replay"]["seconds_per_window"])
    return store.current.status
