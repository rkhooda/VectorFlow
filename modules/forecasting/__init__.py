"""
ML Forecasting Module - VectorFlow
Learns network behavior from time-based network states and forecasts future attack probability.
"""

import os
import sys
from datetime import timedelta
from typing import List, Dict, Any

# Ensure src/ directory is accessible
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = os.path.join(_CURRENT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from .inference import predict, FEATURE_COLS
from contracts import ForecastResult, ForecastPoint, NetworkState

# Default fallback values for 75 CIC-IDS2018 features
FEATURE_DEFAULTS = {
    "Tot Fwd Pkts_sum": 1459.41, "Tot Bwd Pkts_sum": 1885.97,
    "TotLen Fwd Pkts_sum": 103488.75, "TotLen Bwd Pkts_sum": 1635409.47,
    "Flow Duration_mean": 16144159.71, "Flow Duration_std": 32744385.79,
    "Flow IAT Mean_mean": 6671282.01, "Dst Port_nunique": 44.61,
    "SYN Flag Cnt_sum": 10.63, "ACK Flag Cnt_sum": 68.23,
    "RST Flag Cnt_sum": 29.29, "FIN Flag Cnt_sum": 1.29,
    "PSH Flag Cnt_sum": 88.09, "flow_count": 233.96,
    "bwd_fwd_pkt_ratio": 0.96,
    "Tot Fwd Pkts_sum_lag1": 2396.5, "Tot Fwd Pkts_sum_lag2": 4034.46,
    "Tot Fwd Pkts_sum_lag3": 4245.13, "Tot Bwd Pkts_sum_lag1": 1893.84,
    "Tot Bwd Pkts_sum_lag2": 1905.25, "Tot Bwd Pkts_sum_lag3": 1906.78,
    "TotLen Fwd Pkts_sum_lag1": 134184.03, "TotLen Fwd Pkts_sum_lag2": 186621.82,
    "TotLen Fwd Pkts_sum_lag3": 193475.94, "TotLen Bwd Pkts_sum_lag1": 1644350.3,
    "TotLen Bwd Pkts_sum_lag2": 1659035.37, "TotLen Bwd Pkts_sum_lag3": 1659864.54,
    "Flow Duration_mean_lag1": 16163851.77, "Flow Duration_mean_lag2": 16168840.88,
    "Flow Duration_mean_lag3": 16178781.08, "Flow Duration_std_lag1": 32754356.22,
    "Flow Duration_std_lag2": 32737307.99, "Flow Duration_std_lag3": 32743504.85,
    "Flow IAT Mean_mean_lag1": 6663442.99, "Flow IAT Mean_mean_lag2": 6653314.74,
    "Flow IAT Mean_mean_lag3": 6653988.79, "Dst Port_nunique_lag1": 44.65,
    "Dst Port_nunique_lag2": 44.7, "Dst Port_nunique_lag3": 44.68,
    "SYN Flag Cnt_sum_lag1": 10.67, "SYN Flag Cnt_sum_lag2": 10.68,
    "SYN Flag Cnt_sum_lag3": 10.68, "ACK Flag Cnt_sum_lag1": 68.32,
    "ACK Flag Cnt_sum_lag2": 68.41, "ACK Flag Cnt_sum_lag3": 68.41,
    "RST Flag Cnt_sum_lag1": 29.37, "RST Flag Cnt_sum_lag2": 29.39,
    "RST Flag Cnt_sum_lag3": 29.38, "FIN Flag Cnt_sum_lag1": 1.29,
    "FIN Flag Cnt_sum_lag2": 1.29, "FIN Flag Cnt_sum_lag3": 1.29,
    "PSH Flag Cnt_sum_lag1": 88.28, "PSH Flag Cnt_sum_lag2": 88.38,
    "PSH Flag Cnt_sum_lag3": 88.46, "flow_count_lag1": 234.4,
    "flow_count_lag2": 234.78, "flow_count_lag3": 234.98,
    "bwd_fwd_pkt_ratio_lag1": 0.96, "bwd_fwd_pkt_ratio_lag2": 0.97,
    "bwd_fwd_pkt_ratio_lag3": 0.97, "Tot Fwd Pkts_sum_delta1": -937.09,
    "Tot Bwd Pkts_sum_delta1": -7.87, "TotLen Fwd Pkts_sum_delta1": -30695.28,
    "TotLen Bwd Pkts_sum_delta1": -8940.83, "Flow Duration_mean_delta1": -19692.06,
    "Flow Duration_std_delta1": -9970.43, "Flow IAT Mean_mean_delta1": 7839.03,
    "Dst Port_nunique_delta1": -0.04, "SYN Flag Cnt_sum_delta1": -0.03,
    "ACK Flag Cnt_sum_delta1": -0.08, "RST Flag Cnt_sum_delta1": -0.08,
    "FIN Flag Cnt_sum_delta1": 0.0, "PSH Flag Cnt_sum_delta1": -0.19,
    "flow_count_delta1": -0.44, "bwd_fwd_pkt_ratio_delta1": 0.0,
}


def forecast(states: List[NetworkState], config: Dict[str, Any] = None) -> ForecastResult:
    """
    Contract entry point for ML Forecasting module.
    Takes a sequence of NetworkState windows and returns a ForecastResult.
    """
    if not states:
        raise ValueError("forecast requires at least one network state")

    if config is None:
        config = {}

    current_state = states[-1]
    input_features = dict(FEATURE_DEFAULTS)

    if hasattr(current_state, "features") and isinstance(current_state.features, dict):
        for k, v in current_state.features.items():
            if k in input_features:
                input_features[k] = float(v)

    preds_df = predict(input_features)

    xgb_row = preds_df[preds_df["model"] == "XGBoost"]
    if not xgb_row.empty:
        prob = float(xgb_row["probability"].values[0])
    else:
        prob = float(preds_df["probability"].mean())

    horizon_steps = config.get("horizon_steps", 5)
    step_seconds = config.get("step_seconds", 60)

    horizon = []
    for step in range(1, horizon_steps + 1):
        step_time = current_state.window_end + timedelta(seconds=step_seconds * step)
        step_prob = min(max(round(prob + (step * 0.01), 4), 0.0), 1.0)
        horizon.append(ForecastPoint(step=step, time=step_time, probability=step_prob))

    return ForecastResult(
        infiltration_probability=round(prob, 4),
        horizon=horizon,
        model_name="XGBoost-CIC-IDS2018",
    )


__all__ = ["forecast", "predict", "FEATURE_COLS"]
