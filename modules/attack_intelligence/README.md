# Attack Intelligence module

Maps the forecast and the recent traffic to a MITRE ATT&CK stage, explains the
prediction from the features, and flags suspicious flows. Pure rules over the
`contracts/` types: no model files, no network. Entry point:

```python
from modules.attack_intelligence import analyze
result = analyze(states, forecast, config["modules"]["attack_intelligence"])  # -> IntelligenceResult
```

## How the stage is decided

Every feature is compared with its recent baseline: the mean of its `_lag1..3`
features when the pipeline provides them, else the same feature in the previous
three windows. The signed, relative distance from that baseline, clipped to
[-1, 1], is the feature's *deviation*.

Each tactic has a few signal features whose rise is characteristic of it
(`stage_signals` in `config.yaml`: port spread and SYNs for Reconnaissance,
RST/FIN for Initial Access, flow and PSH counts for Lateral Movement, byte totals
for Exfiltration). A tactic's *support* in a window is the mean positive
deviation of its signals. To ignore one-off bursts, support is averaged over the
last `smoothing_windows` windows, and the best such average within the last
`history_windows` windows is kept, so a stage the traffic has recently supported
stays supported while the attack progresses.

The forecast probability sets the bar. Each stage has a probability band (the
mock's: Reconnaissance below 0.25, Initial Access below 0.5, Lateral Movement
below 0.75, Exfiltration above), and a stage needs `min_evidence` support when
the probability is inside or above its band, plus `probability_weight` times the
shortfall when it sits below. The deepest stage whose support clears its bar is
chosen; if none does, Reconnaissance. A probability spike over quiet traffic
therefore never moves the stage, a small probability wobble only nudges the bar,
and traffic alone cannot reach a deep stage while the forecast stays low.
Confidence is the mean of the probability and the chosen stage's support.

The module is stateless, so a probability hovering at a band edge while a
stage's support sits exactly at its bar can still tip the stage between two
values. Hysteresis would need previous results passed through the contract.

## How the explanation is decided

The top 1 to 3 base features (lags and deltas excluded) ranked by absolute
deviation, with the signed deviation as the contribution, plus one sentence:
the leading feature and its distance from baseline, whether the traffic
corroborates the stage, and the forecast risk.

## Flagged flows

Each flow of the current window is scored: 0.5 if its source reached at least
`fanout_min` distinct destinations this window, 0.5 if its bytes exceed
`volume_factor` times the window's median flow, 0.2 if it targets a
`sensitive_ports` port. Flows scoring at least 0.5 are returned, highest first,
with the triggered reasons. CIC-IDS2018 states carry no flows, so the list is
empty there.

## Switching implementations

`config.yaml` → `modules.attack_intelligence.implementation: mock | real`.
Tests: `pytest tests/test_attack_intelligence.py`.
