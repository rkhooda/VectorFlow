"""
inference.py — load saved models and run predictions on new traffic windows
"""

import os
import sys
import joblib
import numpy as np
import pandas as pd
from xgboost import XGBClassifier

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

MODEL_DIR = os.getenv("MODEL_DIR", os.path.join(os.path.dirname(__file__), "models"))
_scaler = joblib.load(os.path.join(MODEL_DIR, "scaler.joblib"))
_logreg = joblib.load(os.path.join(MODEL_DIR, "logreg.joblib"))
_rf     = joblib.load(os.path.join(MODEL_DIR, "randomforest.joblib"))
_xgb    = XGBClassifier()
_xgb.load_model(os.path.join(MODEL_DIR, "xgboost.ubj"))

THRESHOLD = 0.5


def predict(features):
    if isinstance(features, dict):
        df = pd.DataFrame([features])
    elif isinstance(features, pd.DataFrame):
        df = features.copy()
    else:
        raise TypeError("features must be a dict or a pandas DataFrame")

    missing = [c for c in FEATURE_COLS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Input is missing {len(missing)} required feature(s):\n  " +
            "\n  ".join(missing)
        )

    X = df[FEATURE_COLS].values.astype(float)
    X_scaled = _scaler.transform(X)

    results = []
    for name, model in [("LogReg", _logreg), ("RandomForest", _rf), ("XGBoost", _xgb)]:
        proba = model.predict_proba(X_scaled)[:, 1]
        pred  = (proba >= THRESHOLD).astype(int)
        for i, (p, a) in enumerate(zip(proba, pred)):
            results.append({
                "row":              i,
                "model":            name,
                "probability":      round(float(p), 4),
                "attack_predicted": bool(a),
            })

    return pd.DataFrame(results)


if __name__ == "__main__":
    DATA_PATH = os.getenv("DATA_PATH", "data/cic_ids2018_core_training_dataset.csv")

    raw = pd.read_csv(DATA_PATH)
    raw["window_start"] = pd.to_datetime(raw["window_start"])
    test_rows = (
        raw[raw["window_start"] >= "2018-03-01"]
        .head(5)
        .reset_index(drop=True)
    )

    print(f"Running inference on {len(test_rows)} rows from the test period\n")

    preds = predict(test_rows)

    for i in range(len(test_rows)):
        ts     = test_rows.loc[i, "window_start"]
        actual = int(test_rows.loc[i, "Future_Attack_Target"])
        print(f"Row {i}  |  window_start={ts}  |  actual label={actual}")
        row_preds = preds[preds["row"] == i][["model", "probability", "attack_predicted"]]
        print(row_preds.to_string(index=False))
        print()
