"""Simulated replay clock.

ponytail: no background thread — the current window is derived from
wall-clock elapsed time on every request, which is race-free and free.
"""

import time

from backend.app.core import store
from contracts import SessionState


def advance(session: store.Session, seconds_per_window: float) -> int:
    """Sync session.status with the simulated clock.

    Returns the 0-based index of the current window. Only call for sessions
    in the replaying/completed states.
    """
    total = len(session.states)
    elapsed = time.monotonic() - session.replay_started
    seen = min(1 + int(elapsed // seconds_per_window), total)
    session.status.current_window = seen
    if seen >= total:
        session.status.state = SessionState.completed
        session.status.detail = "replay complete"
    else:
        session.status.state = SessionState.replaying
        session.status.detail = f"replaying window {seen}/{total}"
    return seen - 1
