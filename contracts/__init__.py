"""Shared data contracts for SIH26153 — the single source of truth for every
module boundary (see docs/integration.md).

All data exchanged between data_pipeline, forecasting, attack_intelligence
and the backend uses these models. Contract changes are proposed to the tech
lead and land in this package first, in their own commit.
"""

from datetime import datetime
from enum import Enum

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

    infiltration_probability: float = Field(ge=0.0, le=1.0)
    horizon: list[ForecastPoint]  # future timeline, ordered by step
    model_name: str


class AttackStagePrediction(BaseModel):
    """Predicted MITRE ATT&CK stage."""

    tactic_id: str  # e.g. "TA0001"
    tactic_name: str  # e.g. "Initial Access"
    confidence: float = Field(ge=0.0, le=1.0)


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
