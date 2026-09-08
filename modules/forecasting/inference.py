"""
inference.py — Load trained forecasting models lazily and run attack predictions on traffic windows.
"""

import os
import sys
from typing import Dict, Any, List, Union
import numpy as np
import pandas as pd

FEATURE_COLS = [
    "Tot Fwd Pkts_sum", "Tot Bwd Pkts_sum", "TotLen Fwd Pkts_sum",
    "TotLen Bwd Pkts_sum", "Flow Duration_mean", "Flow Duration_std",
    "Flow IAT Mean_mean", "Dst Port_nunique", "SYN Flag Cnt_sum",
    "ACK Flag Cnt_sum", "RST Flag Cnt_sum", "FIN Flag Cnt_sum",
    "PSH Flag Cnt_sum", "flow_count", "bwd_fwd_pkt_ratio",
    "Tot Fwd Pkts_sum_lag1", "Tot Fwd Pkts_sum_lag2", "Tot Fwd Pkts_sum_lag3",
    "Tot Bwd Pkts_sum_lag1", "Tot Bwd Pkts_sum_lag2", "Tot Bwd Pkts_sum_lag3",
    "TotLen Fwd Pkts_sum_lag1", "TotLen Fwd Pkts_sum_lag2", "TotLen Fwd Pkts_sum_lag3",
    "TotLen Bwd Pkts_sum_lag1", "TotLen Bwd Pkts_sum_lag2", "TotLen Bwd Pkts_sum_lag3",
    "Flow Duration_mean_lag1", "Flow Duration_mean_lag2", "Flow Duration_mean_lag3",
    "Flow Duration_std_lag1", "Flow Duration_std_lag2", "Flow Duration_std_lag3",
    "Flow IAT Mean_mean_lag1", "Flow IAT Mean_mean_lag2", "Flow IAT Mean_mean_lag3",
    "Dst Port_nunique_lag1", "Dst Port_nunique_lag2", "Dst Port_nunique_lag3",
    "SYN Flag Cnt_sum_lag1", "SYN Flag Cnt_sum_lag2", "SYN Flag Cnt_sum_lag3",
    "ACK Flag Cnt_sum_lag1", "ACK Flag Cnt_sum_lag2", "ACK Flag Cnt_sum_lag3",
    "RST Flag Cnt_sum_lag1", "RST Flag Cnt_sum_lag2", "RST Flag Cnt_sum_lag3",
    "FIN Flag Cnt_sum_lag1", "FIN Flag Cnt_sum_lag2", "FIN Flag Cnt_sum_lag3",
    "PSH Flag Cnt_sum_lag1", "PSH Flag Cnt_sum_lag2", "PSH Flag Cnt_sum_lag3",
    "flow_count_lag1", "flow_count_lag2", "flow_count_lag3",
    "bwd_fwd_pkt_ratio_lag1", "bwd_fwd_pkt_ratio_lag2", "bwd_fwd_pkt_ratio_lag3",
    "Tot Fwd Pkts_sum_delta1", "Tot Bwd Pkts_sum_delta1",
    "TotLen Fwd Pkts_sum_delta1", "TotLen Bwd Pkts_sum_delta1",
    "Flow Duration_mean_delta1", "Flow Duration_std_delta1",
    "Flow IAT Mean_mean_delta1", "Dst Port_nunique_delta1",
    "SYN Flag Cnt_sum_delta1", "ACK Flag Cnt_sum_delta1",
    "RST Flag Cnt_sum_delta1", "FIN Flag Cnt_sum_delta1",
    "PSH Flag Cnt_sum_delta1", "flow_count_delta1", "bwd_fwd_pkt_ratio_delta1",
]

DEFAULT_MODEL_DIR = os.getenv("MODEL_DIR", os.path.join(os.path.dirname(__file__), "models"))

# Default decision threshold calibrated from validation PR curve (at recall >= 0.5)
DEFAULT_THRESHOLD = 0.15

_SCALER = None
_MODELS = {}


def get_scaler(model_dir: str = None):
    """Lazily load the StandardScaler."""
    global _SCALER
    if _SCALER is None:
        import joblib
        dir_path = model_dir or DEFAULT_MODEL_DIR
        scaler_path = os.path.join(dir_path, "scaler.joblib")
        if not os.path.exists(scaler_path):
            raise FileNotFoundError(
                f"Scaler artifact not found at '{scaler_path}'. "
                f"Please generate models by running 'python modules/forecasting/run.py'."
            )
        _SCALER = joblib.load(scaler_path)
    return _SCALER


def get_model(name: str = "XGBoost", model_dir: str = None):
    """
    Lazily load a specific model artifact on first demand.
    Avoids top-level imports of XGBoost/joblib at package initialization.
    """
    global _MODELS
    if name not in _MODELS:
        dir_path = model_dir or DEFAULT_MODEL_DIR

        if name == "XGBoost":
            try:
                from xgboost import XGBClassifier
            except ImportError as e:
                raise ImportError(
                    "Could not import XGBoost. On macOS, OpenMP is required: "
                    "install it via 'brew install libomp'."
                ) from e

            model_path = os.path.join(dir_path, "xgboost.ubj")
            if not os.path.exists(model_path):
                raise FileNotFoundError(
                    f"XGBoost model file not found at '{model_path}'. "
                    f"Please generate models by running 'python modules/forecasting/run.py'."
                )
            model = XGBClassifier()
            model.load_model(model_path)
            _MODELS[name] = model

        elif name in ("LogReg", "LogisticRegression"):
            import joblib
            model_path = os.path.join(dir_path, "logreg.joblib")
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"LogReg model file not found at '{model_path}'.")
            _MODELS[name] = joblib.load(model_path)

        elif name in ("RandomForest", "RF"):
            import joblib
            model_path = os.path.join(dir_path, "randomforest.joblib")
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"Random Forest model file not found at '{model_path}'.")
            _MODELS[name] = joblib.load(model_path)

        else:
            raise ValueError(f"Unknown model name '{name}'. Supported: 'XGBoost', 'LogReg', 'RandomForest'")

    return _MODELS[name]


def predict(
    features: Union[Dict[str, float], pd.DataFrame],
    models: List[str] = None,
    threshold: float = DEFAULT_THRESHOLD,
    model_dir: str = None,
) -> pd.DataFrame:
    """
    Run prediction on single dict or DataFrame containing required 75 features.
    Raises ValueError if required features are missing.
    """
    if isinstance(features, dict):
        df = pd.DataFrame([features])
    elif isinstance(features, pd.DataFrame):
        df = features.copy()
    else:
        raise TypeError("features must be a dict or a pandas DataFrame")

    missing = [c for c in FEATURE_COLS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Input is missing {len(missing)} required feature(s): {missing[:5]}..."
        )

    if models is None:
        models = ["XGBoost"]

    scaler = get_scaler(model_dir=model_dir)
    X = df[FEATURE_COLS].values.astype(float)
    X_scaled = scaler.transform(X)

    results = []
    for model_name in models:
        model = get_model(model_name, model_dir=model_dir)
        proba = model.predict_proba(X_scaled)[:, 1]
        pred = (proba >= threshold).astype(int)
        for i, (p, a) in enumerate(zip(proba, pred)):
            results.append({
                "row": i,
                "model": model_name,
                "probability": round(float(p), 4),
                "attack_predicted": bool(a),
            })

    return pd.DataFrame(results)


if __name__ == "__main__":
    DATA_PATH = os.getenv("DATA_PATH", "data/cic_ids2018_core_training_dataset.csv")

    if not os.path.exists(DATA_PATH):
        print(f"Dataset not found at {DATA_PATH}. Set DATA_PATH environment variable.")
        sys.exit(1)

    raw = pd.read_csv(DATA_PATH)
    raw["window_start"] = pd.to_datetime(raw["window_start"])
    test_rows = (
        raw[raw["window_start"] >= "2018-03-01"]
        .head(5)
        .reset_index(drop=True)
    )

    print(f"Running inference on {len(test_rows)} test windows\n")
    preds = predict(test_rows, models=["XGBoost", "RandomForest", "LogReg"])

    for i in range(len(test_rows)):
        ts = test_rows.loc[i, "window_start"]
        actual = int(test_rows.loc[i, "Future_Attack_Target"])
        print(f"Row {i} | window_start={ts} | actual label={actual}")
        row_preds = preds[preds["row"] == i][["model", "probability", "attack_predicted"]]
        print(row_preds.to_string(index=False))
        print()
