"""Result APIs — every endpoint answers as of the current replay position."""

from collections import Counter

from fastapi import APIRouter, HTTPException

from backend.app.core import replay, store
from backend.app.core.config import get_config
from contracts import (
    AttackStagePrediction,
    Explanation,
    FlaggedFlow,
    ForecastResult,
    NetworkState,
    SessionState,
    TrafficSummary,
)

router = APIRouter(prefix="/api", tags=["results"])


def _position() -> tuple[store.Session, int]:
    """Current session + 0-based index of the window the replay clock is on."""
    session = store.current
    if session is None:
        raise HTTPException(404, "no session yet — POST /api/session first")
    if session.status.state not in (SessionState.replaying, SessionState.completed):
        raise HTTPException(409, f"session not ready (state: {session.status.state.value})")
    idx = replay.advance(session, get_config()["replay"]["seconds_per_window"])
    return session, idx


@router.get("/state/current", response_model=NetworkState)
def current_state() -> NetworkState:
    session, idx = _position()
    return session.states[idx]


@router.get("/forecast", response_model=ForecastResult)
def forecast() -> ForecastResult:
    session, idx = _position()
    return session.forecasts[idx]


@router.get("/stage", response_model=AttackStagePrediction)
def attack_stage() -> AttackStagePrediction:
    session, idx = _position()
    return session.intelligence[idx].stage


@router.get("/explanations", response_model=Explanation)
def explanations() -> Explanation:
    session, idx = _position()
    return session.intelligence[idx].explanation


@router.get("/flows/flagged", response_model=list[FlaggedFlow])
def flagged_flows() -> list[FlaggedFlow]:
    """All flows flagged so far in the replay, oldest first."""
    session, idx = _position()
    return [f for intel in session.intelligence[: idx + 1] for f in intel.flagged_flows]


@router.get("/traffic/summary", response_model=TrafficSummary)
def traffic_summary() -> TrafficSummary:
    session, idx = _position()
    seen = session.states[: idx + 1]
    bytes_by_src: Counter[str] = Counter()
    protocol_counts: Counter[str] = Counter()
    for state in seen:
        for flow in state.flows:
            bytes_by_src[flow.src_ip] += flow.byte_count
            protocol_counts[flow.protocol] += 1
    return TrafficSummary(
        window_count=len(seen),
        flow_count=sum(s.flow_count for s in seen),
        packet_count=sum(s.packet_count for s in seen),
        byte_count=sum(s.byte_count for s in seen),
        protocol_counts=dict(protocol_counts),
        top_talkers=[ip for ip, _ in bytes_by_src.most_common(5)],
    )
