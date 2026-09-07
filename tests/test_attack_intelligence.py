"""Attack Intelligence contract + behaviour tests (docs/integration.md)."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml

from backend.app.services import mocks
from contracts import ForecastResult, NetworkState
from modules.attack_intelligence import MITRE_STAGES, analyze
from modules.data_pipeline import process
from modules.data_pipeline.build_training_set import BENIGN, USECOLS

CONFIG = yaml.safe_load(Path("config.yaml").read_text())["modules"]
AI_CONFIG = CONFIG["attack_intelligence"]
SAMPLE = Path("data/samples/sample_flows.csv")
ORDER = [t for _, t, _ in MITRE_STAGES]


def check_contract(result):
    assert result.stage.tactic_id in set(ORDER)
    assert 0.0 <= result.stage.confidence <= 1.0
    assert 1 <= len(result.explanation.top_features) <= 3
    assert result.explanation.summary
    for flagged in result.flagged_flows:
        assert flagged.reason
        assert 0.0 <= flagged.score <= 1.0


def quiet_states(overrides=None, n=8) -> list[NetworkState]:
    """Pipeline-shaped states whose features sit exactly on their lag baseline."""
    base = {"SYN Flag Cnt_sum": 4.0, "RST Flag Cnt_sum": 1.0, "Dst Port_nunique": 3.0, "flow_count": 20.0}
    t0 = datetime(2026, 1, 1, 12, 0)
    states = []
    for i in range(n):
        feats = {**base, **(overrides or {}).get(i, {})}
        for k, v in base.items():
            for lag in (1, 2, 3):
                feats[f"{k}_lag{lag}"] = v
            feats[f"{k}_delta1"] = feats[k] - v
        states.append(
            NetworkState(
                window_index=i,
                window_start=t0 + timedelta(seconds=10 * i),
                window_end=t0 + timedelta(seconds=10 * (i + 1)),
                features=feats,
                flows=[],
                flow_count=20,
                packet_count=100,
                byte_count=10_000,
            )
        )
    return states


def forecast_of(prob: float) -> ForecastResult:
    return ForecastResult(infiltration_probability=prob, horizon=[], model_name="fixed")


@pytest.fixture(scope="module")
def sample_states():
    return mocks.process(SAMPLE, CONFIG)


def test_contract_on_sample(sample_states):
    result = analyze(sample_states, mocks.forecast(sample_states, CONFIG), AI_CONFIG)
    check_contract(result)
    # the mock sample carries flows, so the non-empty flagging path runs
    assert any(analyze(sample_states[:i], mocks.forecast(sample_states[:i], CONFIG), AI_CONFIG).flagged_flows
               for i in range(1, len(sample_states) + 1))


def test_stage_never_goes_backwards_as_probability_rises(sample_states):
    prev = 0
    for i in range(1, len(sample_states) + 1):
        seen = sample_states[:i]
        idx = ORDER.index(analyze(seen, mocks.forecast(seen, CONFIG), AI_CONFIG).stage.tactic_id)
        assert idx >= prev  # mock probability rises monotonically across the replay
        prev = idx


def test_pipeline_output_has_no_flows(tmp_path):
    def row(second: int) -> str:
        v = dict.fromkeys(USECOLS, "1")
        v["Timestamp"] = f"01/03/2018 00:{second // 60:02d}:{second % 60:02d}"
        v["Label"] = BENIGN
        return ",".join(v[c] for c in USECOLS)

    csv = tmp_path / "day.csv"
    csv.write_text("\n".join([",".join(USECOLS), *(row(s) for s in range(0, 600, 5))]) + "\n")
    states = process(csv, CONFIG)
    assert states and all(s.flows == [] for s in states)
    result = analyze(states, mocks.forecast(states, CONFIG), AI_CONFIG)
    check_contract(result)
    assert result.flagged_flows == []
    assert "_lag" not in "".join(f.feature for f in result.explanation.top_features)


def test_single_probability_spike_does_not_change_stage():
    states = quiet_states()
    calm = analyze(states, forecast_of(0.05), AI_CONFIG).stage
    spike = analyze(states, forecast_of(0.95), AI_CONFIG).stage
    assert calm.tactic_id == spike.tactic_id == "TA0043"


def test_single_traffic_burst_does_not_change_stage():
    burst = {7: {"SYN Flag Cnt_sum": 7.0}}
    assert analyze(quiet_states(burst), forecast_of(0.6), AI_CONFIG).stage.tactic_id == "TA0043"


def test_sustained_traffic_and_probability_escalate():
    burst = {i: {"SYN Flag Cnt_sum": 7.0} for i in (5, 6, 7)}  # +75% for three windows
    result = analyze(quiet_states(burst), forecast_of(0.6), AI_CONFIG)
    assert result.stage.tactic_id == "TA0001"  # deepest stage both traffic and forecast support
    assert result.explanation.top_features[0].feature == "SYN Flag Cnt_sum"
    assert result.explanation.top_features[0].contribution == pytest.approx(0.75)
    # a low forecast raises the bar, so the same traffic stays at an earlier stage
    assert analyze(quiet_states(burst), forecast_of(0.1), AI_CONFIG).stage.tactic_id == "TA0043"


def test_rejects_empty():
    with pytest.raises(ValueError):
        analyze([], forecast_of(0.5), AI_CONFIG)
