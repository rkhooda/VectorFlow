"""
data.py - load, audit, and split the CIC-IDS2018 dataset
"""

import pandas as pd
import numpy as np


EXCLUDE_DATES = {"2018-02-21"}

TRAIN_DATES = {"2018-02-14", "2018-02-15", "2018-02-22", "2018-02-23"}
VAL_DATES   = {"2018-02-28"}
TEST_DATES  = {"2018-03-01", "2018-03-02"}

TARGET = "Future_Attack_Target"
TIMESTAMP_COL = "window_start"


def load(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df[TIMESTAMP_COL] = pd.to_datetime(df[TIMESTAMP_COL])
    df["date"] = df[TIMESTAMP_COL].dt.date.astype(str)
    return df


def audit(df: pd.DataFrame) -> pd.DataFrame:
    """Print a per-session summary and flag anything suspicious."""
    summary = (
        df.groupby("date")[TARGET]
        .agg(total="count", positives="sum")
        .assign(pos_rate=lambda x: x["positives"] / x["total"])
    )

    print("--- Session audit ---")
    print(summary.to_string())

    feb16 = len(df[df["date"] == "2018-02-16"])
    print(f"\n2018-02-16 rows: {feb16}  "
          f"({'confirmed empty/absent' if feb16 == 0 else 'UNEXPECTED'})")

    suspicious = summary[
        (summary["total"] < 100) | (summary["pos_rate"] > 0.95)
    ]
    if not suspicious.empty:
        print("\nSuspicious sessions (short or near-100% positive rate):")
        print(suspicious.to_string())
    else:
        print("\nNo suspicious sessions besides known exclusions.")

    return summary


def split(df: pd.DataFrame):
    """
    Drop excluded sessions and return (train, val, test) DataFrames.
    Split is purely chronological — no shuffling.
    """
    df = df[~df["date"].isin(EXCLUDE_DATES)].copy()
    print(f"\nAfter dropping {EXCLUDE_DATES}: {len(df):,} rows remain")

    train = df[df["date"].isin(TRAIN_DATES)]
    val   = df[df["date"].isin(VAL_DATES)]
    test  = df[df["date"].isin(TEST_DATES)]

    for name, s in [("Train", train), ("Val", val), ("Test", test)]:
        pos = s[TARGET].sum()
        print(f"  {name:5s}: {len(s):5,} rows | {int(pos):4d} positive "
              f"({100*pos/len(s):.1f}%)")

    return train, val, test


def feature_cols(df: pd.DataFrame) -> list[str]:
    drop = {TIMESTAMP_COL, "date", TARGET}
    return [c for c in df.columns if c not in drop]


def xy(split_df: pd.DataFrame, cols: list[str]):
    X = split_df[cols].values
    y = split_df[TARGET].values.astype(int)
    return X, y
