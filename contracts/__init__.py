"""Shared data contracts for SIH26153 — the single source of truth for every
module boundary (see docs/integration.md).

All data exchanged between data_pipeline, forecasting, attack_intelligence
and the backend uses these models. Contract changes are proposed to the tech
lead and land in this package first, in their own commit.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FlowRecord(BaseModel):
    """One network flow inside a time window."""

    flow_id: str
    src_ip: str
    dst_ip: str
    src_port: int = Field(ge=0, le=65535)
    dst_port: int = Field(ge=0, le=65535)
    protocol: str  # "TCP", "UDP", "ICMP", ...
    start_time: datetime
    end_time: datetime
    packet_count: int = Field(ge=0)
    byte_count: int = Field(ge=0)


class NetworkState(BaseModel):
    """Feature-extracted view of the network for one time window.

    Produced by data_pipeline.process().
    """

    window_index: int = Field(ge=0)
    window_start: datetime
    window_end: datetime
    features: dict[str, float]  # named flow/packet-level features
    flows: list[FlowRecord]
    flow_count: int = Field(ge=0)
    packet_count: int = Field(ge=0)
    byte_count: int = Field(ge=0)


class ForecastPoint(BaseModel):
    """Predicted attack probability for one future time step."""

    step: int = Field(ge=1)  # steps ahead of the current window
    time: datetime
    probability: float = Field(ge=0.0, le=1.0)


class ForecastResult(BaseModel):
    """Produced by forecasting.forecast() for the current replay position."""

    model_config = ConfigDict(protected_namespaces=())

    infiltration_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    horizon: list[ForecastPoint]  # future timeline, ordered by step
    model_name: str
    prediction: bool | None = None
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    forecast_horizon_seconds: dict[str, int] = Field(default_factory=lambda: {"min": 30, "max": 60})
    sequence_length: int | None = Field(default=None, ge=1)
    forecast_ready: bool = True
    status_message: str | None = None
    model_mode: str = "real"
    model_version: str | None = None


class AttackStagePrediction(BaseModel):
    """Predicted MITRE ATT&CK stage."""

    tactic_id: str  # e.g. "TA0001"
    tactic_name: str  # e.g. "Initial Access"
    confidence: float = Field(ge=0.0, le=1.0)
    mitre_technique: str | None = None


class FeatureContribution(BaseModel):
    feature: str
    contribution: float  # signed importance; positive pushes risk up


class Explanation(BaseModel):
    """Why the model predicts this risk/stage."""

    top_features: list[FeatureContribution]  # ordered, most important first
    summary: str


class FlaggedFlow(BaseModel):
    """A suspicious flow with the reason it was flagged."""

    flow: FlowRecord
    reason: str
    score: float = Field(ge=0.0, le=1.0)


class IntelligenceResult(BaseModel):
    """Bundle produced by attack_intelligence.analyze()."""

    stage: AttackStagePrediction
    explanation: Explanation
    flagged_flows: list[FlaggedFlow]
    forecast_ready: bool = True


class TrafficSummary(BaseModel):
    """Basic traffic information over the windows seen so far.

    Computed by the backend from NetworkState — not a module entry point.
    """

    window_count: int = Field(ge=0)
    flow_count: int = Field(ge=0)
    packet_count: int = Field(ge=0)
    byte_count: int = Field(ge=0)
    protocol_counts: dict[str, int]  # protocol -> flow count
    top_talkers: list[str]  # busiest source IPs, busiest first


class SessionState(str, Enum):
    idle = "idle"
    processing = "processing"
    replaying = "replaying"
    completed = "completed"
    error = "error"


class SessionStatus(BaseModel):
    """Lifecycle/progress of the single analysis session."""

    session_id: str
    state: SessionState
    input_file: str | None = None
    total_windows: int = Field(default=0, ge=0)
    current_window: int = Field(default=0, ge=0)  # replay position, 0-based
    detail: str | None = None  # human-readable progress or error message


class SecurityAlert(BaseModel):
    """A deduplicated forecast alert emitted by the backend."""

    alert_id: str
    timestamp: datetime
    attack_probability: float = Field(ge=0.0, le=1.0)
    predicted_stage: str
    mitre_technique: str | None = None
    model_name: str
    model_version: str | None = None
    severity: str
    status: str = "forecast"


class EvidenceRecord(BaseModel):
    """Compact off-chain evidence metadata and its tamper-evident hash."""

    alert_id: str
    timestamp: datetime
    attack_probability: float = Field(ge=0.0, le=1.0)
    predicted_stage: str
    mitre_technique: str | None = None
    model_version: str | None = None
    important_features: list[FeatureContribution] = Field(default_factory=list)
    evidence_hash: str
    ledger_status: str
    transaction_id: str | None = None


class BlockchainVerification(BaseModel):
    alert_id: str
    verified: bool
    evidence_hash: str | None = None
    stored_hash: str | None = None
    message: str


class SystemHealth(BaseModel):
    status: str
    version: str
    model: str
    model_mode: str
    blockchain: str
    replay: str
