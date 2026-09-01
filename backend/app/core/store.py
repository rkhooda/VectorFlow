"""In-memory session store. Restarting the backend clears it (by design)."""

from dataclasses import dataclass, field

from contracts import ForecastResult, IntelligenceResult, NetworkState, SessionStatus


@dataclass
class Session:
    status: SessionStatus
    states: list[NetworkState] = field(default_factory=list)
    forecast: ForecastResult | None = None
    intelligence: IntelligenceResult | None = None


# ponytail: single module-level session — one analysis at a time is all the
# prototype needs; move to a dict keyed by session_id if that ever changes.
current: Session | None = None
