"""
ML Forecasting Module - VectorFlow
Learns network behavior from time-based network states and forecasts future attack probability.
"""

from datetime import timedelta
from typing import List, Dict, Any

from contracts import ForecastResult, ForecastPoint, NetworkState
from .inference import FEATURE_COLS, get_model, get_scaler, DEFAULT_THRESHOLD


def forecast(states: List[NetworkState], config: Dict[str, Any] = None) -> ForecastResult:
    """
    Contract entry point for the ML Forecasting module (see docs/integration.md).
    Takes a sequence of NetworkState windows and returns a ForecastResult.

    Notes:
    - Lazy loading: The XGBoost model and scaler are loaded on first call,
      preventing startup crashes on platforms without OpenMP (libomp).
    - Validation: Raises ValueError if any required features are missing.
    - Horizon: The multi-step horizon projection currently extrapolates from
      the current window probability with dynamic window spacing; full multi-step
      autoregressive sequence forecasting will replace this in the next iteration.
    """
    if not states:
        raise ValueError("forecast requires at least one network state")

    if config is None:
        config = {}

    current_state = states[-1]

    # Validate that current_state contains the full feature set (no silent fallbacks)
    state_features = getattr(current_state, "features", None)
    if not isinstance(state_features, dict):
        raise TypeError(f"Expected current_state.features to be a dict, got {type(state_features)}")

    missing = [f for f in FEATURE_COLS if f not in state_features]
    if missing:
        raise ValueError(
            f"NetworkState (window {current_state.window_index}) is missing {len(missing)} "
            f"required feature(s): {missing[:5]}..."
        )

    # Lazily load only the XGBoost model and scaler
    scaler = get_scaler()
    model = get_model("XGBoost")

    # Construct input vector for inference
    feature_vector = [[float(state_features[col]) for col in FEATURE_COLS]]
    scaled_vector = scaler.transform(feature_vector)

    # Predict attack probability
    proba = float(model.predict_proba(scaled_vector)[:, 1][0])
    current_prob = round(proba, 4)

    # Align with config keys (config.yaml uses 'mock_horizon' / 'horizon')
    horizon_steps = config.get("horizon", config.get("mock_horizon", 5))

    # Determine window step duration from actual window timestamps (default 10s for CIC-IDS2018)
    if current_state.window_end and current_state.window_start:
        step_delta = current_state.window_end - current_state.window_start
        if step_delta.total_seconds() <= 0:
            step_delta = timedelta(seconds=10)
    else:
        step_delta = timedelta(seconds=10)

    # Multi-step horizon timeline (linear placeholder extrapolation)
    horizon = []
    for step in range(1, horizon_steps + 1):
        step_time = current_state.window_end + (step_delta * step)
        step_prob = min(max(round(current_prob + (step * 0.01), 4), 0.0), 1.0)
        horizon.append(ForecastPoint(step=step, time=step_time, probability=step_prob))

    return ForecastResult(
        infiltration_probability=current_prob,
        horizon=horizon,
        model_name="XGBoost-CIC-IDS2018",
    )


__all__ = ["forecast", "FEATURE_COLS", "DEFAULT_THRESHOLD"]
