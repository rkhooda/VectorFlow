"""In-memory session store. Restarting the backend clears it (by design)."""

from dataclasses import dataclass, field

from contracts import (
    EvidenceRecord,
    ForecastResult,
    IntelligenceResult,
    NetworkState,
    SecurityAlert,
    SessionStatus,
)


@dataclass
class Session:
    status: SessionStatus
    states: list[NetworkState] = field(default_factory=list)
    # index i → result computed on the windows seen up to and including i
    forecasts: list[ForecastResult | None] = field(default_factory=list)
    intelligence: list[IntelligenceResult | None] = field(default_factory=list)
    alerts: list[SecurityAlert] = field(default_factory=list)
    evidence: dict[str, EvidenceRecord] = field(default_factory=dict)
    replay_started: float = 0.0  # time.monotonic() when replay began


# ponytail: single module-level session — one analysis at a time is all the
# prototype needs; move to a dict keyed by session_id if that ever changes.
current: Session | None = None
