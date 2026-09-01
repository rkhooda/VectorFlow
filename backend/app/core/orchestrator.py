"""Runs the analysis pipeline: process → forecast → analyze.

Currently wired to the mocks; Phase 5 swaps each call for the real module
(docs/implementation-plan.md).
"""

import time
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
        # precompute results per replay position so result endpoints only index
        for i in range(1, len(session.states) + 1):
            seen = session.states[:i]
            forecast = mocks.forecast(seen, module_config)
            session.forecasts.append(forecast)
            session.intelligence.append(mocks.analyze(seen, forecast, module_config))
        total = len(session.states)
        session.status.total_windows = total
        session.status.current_window = 1
        session.status.state = SessionState.replaying
        session.status.detail = f"replaying window 1/{total}"
        session.replay_started = time.monotonic()
    except Exception as exc:  # module code is a trust boundary — never crash the API
        session.status.state = SessionState.error
        session.status.detail = f"analysis failed: {exc}"
    return session
