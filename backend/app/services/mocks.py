"""Mock implementations of the three team modules.

Same entry-point signatures as the real modules (docs/integration.md), so
backend and dashboard development never blocks on teammates. Data is fully
deterministic per input path, and the scenario escalates across the capture
so a replay looks like a real infiltration building up:
low activity → rising probability → later MITRE stages → flagged flows.
"""

import hashlib
import random
from datetime import datetime, timedelta
from pathlib import Path

from contracts import (
    AttackStagePrediction,
    Explanation,
    FeatureContribution,
    FlaggedFlow,
    FlowRecord,
    ForecastPoint,
    ForecastResult,
    IntelligenceResult,
    NetworkState,
)

WINDOW_SECONDS = 60
CAPTURE_START = datetime(2026, 1, 1, 12, 0, 0)  # fixed → deterministic output
PROTOCOLS = ["TCP", "UDP", "ICMP"]
FEATURE_NAMES = [
    "mean_packet_size",
    "flow_rate",
    "unique_dst_ports",
    "syn_ratio",
    "bytes_per_flow",
    "failed_conn_ratio",
    "external_dst_ratio",
]

# (upper probability bound, tactic id, tactic name) — checked in order
MITRE_STAGES = [
    (0.25, "TA0043", "Reconnaissance"),
    (0.50, "TA0001", "Initial Access"),
    (0.75, "TA0008", "Lateral Movement"),
    (1.01, "TA0010", "Exfiltration"),
]


def process(input_path: Path, config: dict) -> list[NetworkState]:
    """Mock data_pipeline.process(): fake time-windowed network states."""
    rng = random.Random(int(hashlib.md5(str(input_path).encode()).hexdigest(), 16))
    total = config.get("mock_windows", 20)
    states = []
    for i in range(total):
        level = i / max(total - 1, 1)  # 0 → 1 escalation across the capture
        w_start = CAPTURE_START + timedelta(seconds=WINDOW_SECONDS * i)
        w_end = w_start + timedelta(seconds=WINDOW_SECONDS)
        flows = [
            FlowRecord(
                flow_id=f"w{i}-f{f}",
                src_ip=f"10.0.{rng.randint(0, 3)}.{rng.randint(2, 254)}",
                dst_ip=f"192.168.1.{rng.randint(2, 254)}",
                src_port=rng.randint(1024, 65535),
                dst_port=rng.choice([22, 53, 80, 443, 445, 3389]),
                protocol=rng.choice(PROTOCOLS),
                start_time=w_start,
                end_time=w_end,
                packet_count=(packets := rng.randint(10, 500)),
                byte_count=packets * rng.randint(60, 1500),
            )
            for f in range(rng.randint(5, 10))
        ]
        states.append(
            NetworkState(
                window_index=i,
                window_start=w_start,
                window_end=w_end,
                features={
                    name: round(rng.uniform(0.1, 0.4) + 0.6 * level, 4)
                    for name in FEATURE_NAMES
                },
                flows=flows,
                flow_count=len(flows),
                packet_count=sum(fl.packet_count for fl in flows),
                byte_count=sum(fl.byte_count for fl in flows),
            )
        )
    return states


def forecast(states: list[NetworkState], config: dict) -> ForecastResult:
    """Mock forecasting.forecast(): probability tracks the escalation level.

    Works on any prefix of the capture, so replay (Phase 3) can call it with
    states seen "so far".
    """
    if not states:
        raise ValueError("forecast requires at least one network state")
    current = states[-1]
    signal = sum(current.features.values()) / len(current.features)
    prob = min(round(signal, 4), 1.0)
    horizon = [
        ForecastPoint(
            step=step,
            time=current.window_end + timedelta(seconds=WINDOW_SECONDS * step),
            probability=min(round(prob + 0.05 * step, 4), 1.0),
        )
        for step in range(1, config.get("mock_horizon", 5) + 1)
    ]
    return ForecastResult(
        infiltration_probability=prob,
        horizon=horizon,
        model_name="mock-forecaster-v0",
    )


def analyze(
    states: list[NetworkState], forecast_result: ForecastResult, config: dict
) -> IntelligenceResult:
    """Mock attack_intelligence.analyze(): stage, explanation, flagged flows."""
    if not states:
        raise ValueError("analyze requires at least one network state")
    prob = forecast_result.infiltration_probability
    for bound, tactic_id, tactic_name in MITRE_STAGES:
        if prob < bound:
            stage = AttackStagePrediction(
                tactic_id=tactic_id,
                tactic_name=tactic_name,
                confidence=round(min(0.6 + prob / 3, 1.0), 4),
            )
            break
    current = states[-1]
    top = sorted(current.features.items(), key=lambda kv: kv[1], reverse=True)[:3]
    explanation = Explanation(
        top_features=[
            FeatureContribution(feature=name, contribution=value)
            for name, value in top
        ],
        summary=(
            f"[mock] {top[0][0]} is the strongest driver of the "
            f"{stage.tactic_name} prediction."
        ),
    )
    flagged = [
        FlaggedFlow(
            flow=fl,
            reason="[mock] unusually high packet count for this window",
            score=min(round(fl.packet_count / 500, 4), 1.0),
        )
        for fl in current.flows
        if fl.packet_count > 400
    ]
    return IntelligenceResult(stage=stage, explanation=explanation, flagged_flows=flagged)
