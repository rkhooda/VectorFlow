"""
evaluate.py - metrics, comparison table, confusion matrices
"""

import pandas as pd
import numpy as np
from sklearn.metrics import (
    average_precision_score,
    roc_auc_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
)


def evaluate_one(model, X, y, model_name: str, split_label: str) -> dict:
    proba = model.predict_proba(X)[:, 1]
    pred  = model.predict(X)
    cm    = confusion_matrix(y, pred)

    return {
        "model":     model_name,
        "split":     split_label,
        "PR-AUC":    round(average_precision_score(y, proba), 4),
        "ROC-AUC":   round(roc_auc_score(y, proba), 4),
        "Precision": round(precision_score(y, pred, zero_division=0), 4),
        "Recall":    round(recall_score(y, pred), 4),
        "F1":        round(f1_score(y, pred), 4),
        "TP": int(cm[1, 1]),
        "FP": int(cm[0, 1]),
        "FN": int(cm[1, 0]),
        "TN": int(cm[0, 0]),
    }


def evaluate_all(models: dict, splits: dict) -> pd.DataFrame:
    """
    models: {"ModelName": fitted_model, ...}
    splits: {"train": (X, y), "val": (X, y), "test": (X, y)}
    Returns a DataFrame with one row per (model, split) combination.
    """
    rows = []
    for model_name, model in models.items():
        for split_label, (X, y) in splits.items():
            rows.append(evaluate_one(model, X, y, model_name, split_label))
    return pd.DataFrame(rows)


def print_comparison(results: pd.DataFrame):
    print("\n\n===== Model Comparison =====\n")

    metric_cols = ["PR-AUC", "ROC-AUC", "Precision", "Recall", "F1"]
    pivot = results.pivot_table(
        index="model",
        columns="split",
        values=metric_cols,
        aggfunc="first",
    )
    pivot = pivot.reindex(["train", "val", "test"], axis=1, level="split")
    print(pivot.to_string(float_format="%.4f"))

    print("\n\n===== Confusion Matrices =====\n")
    print(results[["model", "split", "TP", "FP", "FN", "TN"]].to_string(index=False))

    print(
        "\nNote on accuracy: with ~8-9% positives in train, a dummy 'always-negative' "
        "classifier reaches ~91% accuracy while catching zero attacks. "
        "PR-AUC and F1 are the metrics that matter here."
    )
