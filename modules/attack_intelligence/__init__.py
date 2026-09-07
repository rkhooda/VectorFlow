"""Attack Intelligence: forecast + recent traffic -> MITRE stage, explanation, flagged flows.

Pure rules and arithmetic over the contract types, fully offline. README.md
explains how the stage and the explanation are decided; `config.yaml`
(`modules.attack_intelligence`) holds the tunables read from `config`.
"""

from __future__ import annotations

from statistics import fmean, median

from contracts import (
    AttackStagePrediction,
    Explanation,
    FeatureContribution,
    FlaggedFlow,
    FlowRecord,
    ForecastResult,
    IntelligenceResult,
    NetworkState,
)

# (upper probability bound, tactic id, tactic name), same bands as the mock:
# a stage's band starts where the previous one ends.
MITRE_STAGES = [
    (0.25, "TA0043", "Reconnaissance"),
    (0.50, "TA0001", "Initial Access"),
    (0.75, "TA0008", "Lateral Movement"),
    (1.01, "TA0010", "Exfiltration"),
]

# features whose rise is characteristic of each tactic (data_pipeline names);
# a feature missing from the state is ignored. Override in config.yaml.
STAGE_SIGNALS = {
    "TA0043": ["Dst Port_nunique", "SYN Flag Cnt_sum", "flow_count"],
    "TA0001": ["RST Flag Cnt_sum", "FIN Flag Cnt_sum", "SYN Flag Cnt_sum"],
    "TA0008": ["flow_count", "PSH Flag Cnt_sum", "Tot Fwd Pkts_sum"],
    "TA0010": ["TotLen Fwd Pkts_sum", "TotLen Bwd Pkts_sum", "bwd_fwd_pkt_ratio"],
}


def analyze(states: list[NetworkState], forecast: ForecastResult, config: dict) -> IntelligenceResult:
    """Entry point (docs/integration.md)."""
    if not states:
        raise ValueError("analyze requires at least one network state")
    prob = forecast.infiltration_probability
    signals = config.get("stage_signals", STAGE_SIGNALS)
    smoothing = config.get("smoothing_windows", 3)
    history = config.get("history_windows", 30)
    min_evidence = config.get("min_evidence", 0.35)

    # per-tactic support: best `smoothing`-window average within the last
    # `history` windows, so one burst counts 1/smoothing and stages do not flap
    n = len(states)
    per_window = [_evidence(states, i, signals) for i in range(max(0, n - history - smoothing + 1), n)]
    support = {
        tactic: max(sum(w[tactic] for w in per_window[max(0, k - smoothing + 1) : k + 1]) / smoothing
                    for k in range(len(per_window)))
        for tactic in signals
    }

    # deepest stage the traffic supports wins; the further the forecast sits
    # below a stage's probability band, the more support that stage needs, so a
    # probability wobble moves the bar a little instead of toggling the stage.
    # ponytail: stateless, so a probability hovering at a band edge while support
    # sits at the bar can still tip the stage; pass previous results through the
    # contract if hysteresis is ever needed.
    weight = config.get("probability_weight", 2.0)
    lower = [0.0, *(bound for bound, _, _ in MITRE_STAGES[:-1])]
    idx = max(
        (i for i, (_, tactic, _) in enumerate(MITRE_STAGES)
         if support.get(tactic, 0.0) >= min_evidence + weight * max(0.0, lower[i] - prob)),
        default=0,
    )
    _, tactic_id, tactic_name = MITRE_STAGES[idx]
    corroborated = support.get(tactic_id, 0.0)
    stage = AttackStagePrediction(
        tactic_id=tactic_id,
        tactic_name=tactic_name,
        confidence=round(min(0.5 * prob + 0.5 * corroborated, 1.0), 4),
    )

    return IntelligenceResult(
        stage=stage,
        explanation=_explain(states, stage, prob, corroborated >= min_evidence),
        flagged_flows=_flag(states[-1].flows, config),
    )


def _baseline(name: str, states: list[NetworkState], i: int) -> float | None:
    """Recent baseline of a feature at window i: its lag features, else the previous windows."""
    cur = states[i].features
    lags = [cur[k] for k in (f"{name}_lag1", f"{name}_lag2", f"{name}_lag3") if k in cur]
    if not lags:
        lags = [s.features[name] for s in states[max(0, i - 3) : i] if name in s.features]
    return fmean(lags) if lags else None


def _deviation(name: str, states: list[NetworkState], i: int) -> float:
    """Signed relative distance of a feature from its baseline, clipped to [-1, 1]."""
    base = _baseline(name, states, i)
    if base is None:
        return 0.0
    return max(-1.0, min(1.0, (states[i].features[name] - base) / (abs(base) + 1e-9)))


def _evidence(states: list[NetworkState], i: int, signals: dict) -> dict[str, float]:
    """Per tactic: mean positive deviation of its signal features at window i, in [0, 1]."""
    present = states[i].features
    return {
        tactic: fmean([max(0.0, _deviation(f, states, i)) for f in feats if f in present] or [0.0])
        for tactic, feats in signals.items()
    }


def _explain(states: list[NetworkState], stage: AttackStagePrediction, prob: float, corroborated: bool) -> Explanation:
    """Top 1-3 base features by distance from baseline, plus one plain sentence."""
    i = len(states) - 1
    base_features = [f for f in states[i].features if "_lag" not in f and not f.endswith("_delta1")]
    ranked = sorted(((f, _deviation(f, states, i)) for f in base_features), key=lambda fd: abs(fd[1]), reverse=True)
    top = [fd for fd in ranked[:3] if fd[1] != 0.0] or ranked[:1]

    name, dev = top[0]
    if dev == 0.0:
        driver = "No feature departs from its recent baseline"
    else:
        pct = f"{abs(dev):.0%}" if abs(dev) < 1 else "over 100%"
        driver = f"{name} is {pct} {'above' if dev > 0 else 'below'} its recent baseline"
    verdict = (
        f"traffic supports the {stage.tactic_name} stage" if corroborated
        else "traffic does not corroborate a later stage"
    )
    return Explanation(
        top_features=[FeatureContribution(feature=f, contribution=round(d, 4)) for f, d in top],
        summary=f"{driver}; {verdict} (forecast risk {prob:.0%}).",
    )


def _flag(flows: list[FlowRecord], config: dict) -> list[FlaggedFlow]:
    """Score each flow of the current window; empty input (CIC-IDS2018) gives []."""
    if not flows:
        return []
    fanout_min = config.get("fanout_min", 3)
    volume_factor = config.get("volume_factor", 3.0)
    sensitive = set(config.get("sensitive_ports", [21, 22, 23, 445, 3389]))
    median_bytes = max(median(f.byte_count for f in flows), 1)
    targets: dict[str, set] = {}
    for f in flows:
        targets.setdefault(f.src_ip, set()).add((f.dst_ip, f.dst_port))

    flagged = []
    for f in flows:
        score, reasons = 0.0, []
        if len(targets[f.src_ip]) >= fanout_min:
            score += 0.5
            reasons.append(f"{f.src_ip} reached {len(targets[f.src_ip])} destinations this window")
        if f.byte_count > volume_factor * median_bytes:
            score += 0.5
            reasons.append(f"{f.byte_count / median_bytes:.0f}x the window's median bytes")
        if f.dst_port in sensitive:
            score += 0.2
            reasons.append(f"sensitive port {f.dst_port}")
        if score >= 0.5:  # fan-out or volume; a sensitive port alone is not enough
            flagged.append(FlaggedFlow(flow=f, reason="; ".join(reasons), score=min(score, 1.0)))
    return sorted(flagged, key=lambda x: x.score, reverse=True)
