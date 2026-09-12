"""Security alert and evidence APIs."""

from fastapi import APIRouter, HTTPException

from backend.app.core import orchestrator, replay, store
from backend.app.core.config import get_config
from backend.app.services.blockchain_service import get_ledger
from contracts import BlockchainVerification, EvidenceRecord, SecurityAlert

router = APIRouter(prefix="/api", tags=["evidence"])


def _session() -> store.Session:
    if store.current is None:
        raise HTTPException(404, "no session yet — POST /api/session first")
    return store.current


def _materialize() -> store.Session:
    session = _session()
    if session.status.state.value in ("replaying", "completed"):
        index = replay.advance(session, get_config()["replay"]["seconds_per_window"])
        orchestrator.ensure_results(session, index, get_config())
    return session


@router.get("/alerts", response_model=list[SecurityAlert])
def alerts() -> list[SecurityAlert]:
    return _materialize().alerts


@router.get("/evidence", response_model=list[EvidenceRecord])
def evidence() -> list[EvidenceRecord]:
    return list(_materialize().evidence.values())


@router.get("/evidence/{alert_id}/verify", response_model=BlockchainVerification)
def verify(alert_id: str) -> BlockchainVerification:
    session = _session()
    if alert_id not in session.evidence:
        raise HTTPException(404, "evidence record not found")
    ledger = get_ledger(get_config().get("blockchain", {}))
    if ledger is None:
        return BlockchainVerification(alert_id=alert_id, verified=False, message="Blockchain ledger disabled")
    try:
        return ledger.verify(alert_id)
    except (OSError, ValueError, TypeError) as exc:
        return BlockchainVerification(alert_id=alert_id, verified=False, message=f"Blockchain ledger unavailable: {exc}")
