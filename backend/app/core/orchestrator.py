"""Runs the analysis pipeline: process → forecast → analyze.

`backend.app.services` resolves each call to the mock or the real module
(config.yaml, `modules.<module>.implementation`).
"""

import time
import uuid
from pathlib import Path

from backend.app.core import store
from backend.app import services
from contracts import EvidenceRecord, ForecastResult, IntelligenceResult, SecurityAlert, SessionState, SessionStatus
from backend.app.services.blockchain_service import get_ledger


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
        session.states = services.process(input_path, module_config)
        if not session.states:
            raise ValueError("no analyzable traffic windows in the capture")
        total = len(session.states)
        session.forecasts = [None] * total
        session.intelligence = [None] * total
        session.status.total_windows = total
        session.status.current_window = 1
        session.status.state = SessionState.replaying
        session.status.detail = f"replaying window 1/{total}"
        session.replay_started = time.monotonic()
    except Exception as exc:  # module code is a trust boundary — never crash the API
        session.status.state = SessionState.error
        session.status.detail = f"analysis failed: {exc}"
    return session


def ensure_results(session: store.Session, index: int, module_config: dict) -> tuple[ForecastResult, IntelligenceResult]:
    """Compute the requested replay position once, using real history."""
    modules_config = module_config.get("modules", module_config)
    for position in range(index + 1):
        if session.forecasts[position] is not None:
            continue
        seen = session.states[: position + 1]
        forecast = services.forecast(seen, modules_config)
        intelligence = services.analyze(seen, forecast, modules_config.get("attack_intelligence", {}))
        session.forecasts[position] = forecast
        session.intelligence[position] = intelligence
        _maybe_create_alert(session, position, forecast, intelligence, module_config)
    return session.forecasts[index], session.intelligence[index]


def _maybe_create_alert(session: store.Session, index: int, forecast: ForecastResult, intelligence: IntelligenceResult, config: dict) -> None:
    if not forecast.forecast_ready or forecast.infiltration_probability is None:
        return
    threshold = float(config.get("blockchain", {}).get("alert_threshold", config.get("alert_threshold", 0.5)))
    if forecast.infiltration_probability < threshold:
        return
    previously_high = any(
        f is not None and f.forecast_ready and f.infiltration_probability is not None and f.infiltration_probability >= threshold
        for f in session.forecasts[:index]
    )
    if previously_high:
        return
    alert = SecurityAlert(
        alert_id=f"{session.status.session_id}-a{index + 1:04d}",
        timestamp=session.states[index].window_end,
        attack_probability=forecast.infiltration_probability,
        predicted_stage=intelligence.stage.tactic_name,
        mitre_technique=intelligence.stage.mitre_technique,
        model_name=forecast.model_name,
        model_version=forecast.model_version,
        severity="high" if forecast.infiltration_probability >= 0.75 else "elevated",
    )
    session.alerts.append(alert)
    ledger_cfg = config.get("blockchain", {})
    ledger = get_ledger(ledger_cfg)
    if ledger is None:
        return
    try:
        session.evidence[alert.alert_id] = ledger.record(alert, intelligence.explanation)
    except (OSError, ValueError, TypeError) as exc:
        # Forecasting and alerting remain available when the audit layer is down.
        session.evidence[alert.alert_id] = EvidenceRecord(
            alert_id=alert.alert_id,
            timestamp=alert.timestamp,
            attack_probability=alert.attack_probability,
            predicted_stage=alert.predicted_stage,
            mitre_technique=alert.mitre_technique,
            model_version=alert.model_version,
            important_features=intelligence.explanation.top_features,
            evidence_hash="",
            ledger_status=f"unavailable: {exc}",
        )
