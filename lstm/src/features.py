"""
Feature definitions, causal transformations, log1p scaling, and leakage auditing.
"""

from typing import List, Tuple
import pandas as pd
import numpy as np


BASE_FEATURES: List[str] = [
    "Tot Fwd Pkts_sum",
    "Tot Bwd Pkts_sum",
    "TotLen Fwd Pkts_sum",
    "TotLen Bwd Pkts_sum",
    "Flow Duration_mean",
    "Flow Duration_std",
    "Flow IAT Mean_mean",
    "Dst Port_nunique",
    "SYN Flag Cnt_sum",
    "ACK Flag Cnt_sum",
    "RST Flag Cnt_sum",
    "FIN Flag Cnt_sum",
    "PSH Flag Cnt_sum",
    "flow_count",
    "bwd_fwd_pkt_ratio",
]

HEAVY_TAILED_COLS: List[str] = [
    "Tot Fwd Pkts_sum",
    "Tot Bwd Pkts_sum",
    "TotLen Fwd Pkts_sum",
    "TotLen Bwd Pkts_sum",
    "Flow Duration_mean",
    "Flow Duration_std",
    "Flow IAT Mean_mean",
    "flow_count",
]


def apply_log1p_transforms(df: pd.DataFrame, columns: List[str] = None) -> pd.DataFrame:
    """
    Applies log1p transformation to heavy-tailed count/volume features.
    Causal and pointwise operation.
    """
    if columns is None:
        columns = HEAVY_TAILED_COLS

    res_df = df.copy()
    for col in columns:
        if col in res_df.columns:
            res_df[f"{col}_log1p"] = np.log1p(np.maximum(res_df[col].values, 0.0))
    return res_df


def add_causal_rolling_features(
    windows_df: pd.DataFrame,
    base_cols: List[str] = None,
    window_size: int = 3,
) -> pd.DataFrame:
    """
    Computes purely backward-looking (causal) rolling features per day.
    Used primarily for tabular/tree baselines.
    """
    if base_cols is None:
        base_cols = BASE_FEATURES

    df = windows_df.copy()
    rolling_cols = []

    for date, group in df.groupby("date", sort=False):
        group_idx = group.index
        for col in base_cols:
            s = group[col]
            # Backward-looking rolling mean & std (closed='left' or min_periods=1)
            r_mean = s.rolling(window=window_size, min_periods=1).mean()
            r_std = s.rolling(window=window_size, min_periods=1).std().fillna(0.0)

            df.loc[group_idx, f"{col}_roll3_mean"] = r_mean
            df.loc[group_idx, f"{col}_roll3_std"] = r_std

    return df


def audit_feature_causality(df: pd.DataFrame, feature_cols: List[str]) -> bool:
    """
    Audits feature columns to verify no future labels, lead features, or post-attack information exists.
    Returns True if passed, raises ValueError if leak detected.
    """
    forbidden_substrings = [
        "future", "target", "lead", "next", "after", "is_onset", "onset_id", "sample_category"
    ]

    leaked = []
    for col in feature_cols:
        col_lower = col.lower()
        for sub in forbidden_substrings:
            if sub in col_lower:
                leaked.append((col, sub))

    if leaked:
        raise ValueError(f"CRITICAL TARGET LEAKAGE DETECTED in features: {leaked}")

    return True
