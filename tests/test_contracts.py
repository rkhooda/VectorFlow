"""Contract tests — validate any implementation of the module entry points.

Run against the mocks now; module owners run the same suite against their
real code before integration (docs/integration.md). Pydantic enforces types
and value ranges on construction; these tests add cross-field guarantees.
"""

from pathlib import Path

import pytest

from backend.app.services import mocks

CONFIG = {"mock_windows": 12, "mock_horizon": 5}
INPUT = Path("data/samples/fake.csv")


@pytest.fixture(scope="module")
def states():
    return mocks.process(INPUT, CONFIG)


def test_process_contract(states):
    assert len(states) == CONFIG["mock_windows"]
    for i, s in enumerate(states):
        assert s.window_index == i
        assert s.window_start < s.window_end
        assert s.features and all(isinstance(v, float) for v in s.features.values())
        assert s.flow_count == len(s.flows) > 0
        assert s.packet_count == sum(f.packet_count for f in s.flows)
        assert s.byte_count == sum(f.byte_count for f in s.flows)
    for prev, cur in zip(states, states[1:]):
        assert prev.window_end <= cur.window_start


def test_process_deterministic(states):
    assert mocks.process(INPUT, CONFIG) == states


def test_forecast_contract(states):
    result = mocks.forecast(states, CONFIG)
    assert 0.0 <= result.infiltration_probability <= 1.0
    assert [p.step for p in result.horizon] == list(range(1, CONFIG["mock_horizon"] + 1))
    for point in result.horizon:
        assert 0.0 <= point.probability <= 1.0
        assert point.time > states[-1].window_end or point.step == 0
    assert result.model_name


def test_forecast_escalates_over_replay(states):
    early = mocks.forecast(states[:2], CONFIG).infiltration_probability
    late = mocks.forecast(states, CONFIG).infiltration_probability
    assert late > early


def test_forecast_rejects_empty():
    with pytest.raises(ValueError):
        mocks.forecast([], CONFIG)


def test_analyze_contract(states):
    result = mocks.analyze(states, mocks.forecast(states, CONFIG), CONFIG)
    assert result.stage.tactic_id in {t for _, t, _ in mocks.MITRE_STAGES}
    assert 0.0 <= result.stage.confidence <= 1.0
    assert 1 <= len(result.explanation.top_features) <= 3
    assert result.explanation.summary
    for flagged in result.flagged_flows:
        assert flagged.reason
        assert 0.0 <= flagged.score <= 1.0


def test_analyze_stage_follows_probability(states):
    # early in the capture the predicted stage should be earlier in the
    # kill chain than at the end
    order = [t for _, t, _ in mocks.MITRE_STAGES]
    early = mocks.analyze(states[:2], mocks.forecast(states[:2], CONFIG), CONFIG)
    late = mocks.analyze(states, mocks.forecast(states, CONFIG), CONFIG)
    assert order.index(early.stage.tactic_id) <= order.index(late.stage.tactic_id)
