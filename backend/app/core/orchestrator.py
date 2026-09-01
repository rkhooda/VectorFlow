"""Runs the analysis pipeline: process → forecast → analyze.

Currently wired to the mocks; Phase 5 swaps each call for the real module
(docs/implementation-plan.md).
"""

import uuid
from pathlib import Path

from backend.app.core import store
from backend.app.services import mocks
from contracts import SessionState, SessionStatus


def run(input_path: Path, module_config: dict) -> store.Session:
    """Analyze one input file and make it the current session."""
    session = store.Session(
        status=SessionStatus(
            session_id=uuid.uuid4().hex[:8],
            state=SessionState.processing,
            input_file=input_path.name,
        )
    )
    store.current = session
    try:
        session.states = mocks.process(input_path, module_config)
        session.forecast = mocks.forecast(session.states, module_config)
        session.intelligence = mocks.analyze(
            session.states, session.forecast, module_config
        )
        session.status.total_windows = len(session.states)
        session.status.current_window = len(session.states)
        session.status.state = SessionState.completed
        session.status.detail = "analysis complete"
    except Exception as exc:  # module code is a trust boundary — never crash the API
        session.status.state = SessionState.error
        session.status.detail = f"analysis failed: {exc}"
    return session
