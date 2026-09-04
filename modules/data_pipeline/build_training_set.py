"""Build the 10-second window forecasting dataset from raw CIC-IDS-2018 flow CSVs.

Replaces the hand-made `*_processed_states.parquet`, which leaked the current
window into its "future attack" label, dropped every backward-traffic column,
and filled the capture gap with zeros as if it were quiet traffic.

    python -m modules.data_pipeline.build_training_set data/03-01-2018.csv
    python -m modules.data_pipeline.build_training_set data/raw/*.csv --core
    python -m modules.data_pipeline.build_training_set --self-check

Each day is windowed independently, so no lag, delta or target ever reaches
across a capture boundary.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

WINDOW = "10s"
HORIZON = 3  # forecast windows ahead (3 x 10s = 30s lead time)
LAGS = (1, 2, 3)  # past 10s / 20s / 30s
BENIGN = "Benign"

# raw column -> aggregations applied per window
AGG = {
    "Tot Fwd Pkts": ["sum"],
    "Tot Bwd Pkts": ["sum"],
    "TotLen Fwd Pkts": ["sum"],
    "TotLen Bwd Pkts": ["sum"],
    "Flow Duration": ["mean", "std"],
    "Flow IAT Mean": ["mean"],
    "Dst Port": ["nunique"],
    "SYN Flag Cnt": ["sum"],
    "ACK Flag Cnt": ["sum"],
    "RST Flag Cnt": ["sum"],
    "FIN Flag Cnt": ["sum"],
    "PSH Flag Cnt": ["sum"],
}
USECOLS = ["Timestamp", "Label", *AGG]

# derived from the label, or plain bookkeeping: never a model input
LABEL_COLS = ["Slice_Attack", "attack_flow_count", "attack_types",
              "windows_to_next_onset", "next_attack_type", "is_gap"]


def _parse_timestamps(s: pd.Series) -> pd.Series:
    """CIC files are day-first; a few days switch to 12-hour AM/PM mid-file."""
    ts = pd.to_datetime(s, format="%d/%m/%Y %H:%M:%S", errors="coerce")
    if ts.isna().any():
        rest = pd.to_datetime(s[ts.isna()], format="mixed", dayfirst=True, errors="coerce")
        ts = ts.fillna(rest)
    return ts


def _first_occurrence_mask(csv_path: Path) -> np.ndarray:
    """True for the first appearance of each raw data line.

    Duplicates must be judged on the WHOLE row: two flows can be identical in the
    dozen columns we aggregate and still be distinct flows. Hashing raw lines gets
    that exactly without ever holding all ~80 parsed columns in memory.
    """
    parts, buf = [], []
    with open(csv_path, "rb") as fh:
        fh.readline()  # header
        for line in fh:
            buf.append(hash(line))
            if len(buf) >= 4_000_000:
                parts.append(np.fromiter(buf, np.int64, len(buf)))
                buf.clear()
    parts.append(np.fromiter(buf, np.int64, len(buf)))
    hashes = np.concatenate(parts)
    keep = np.zeros(len(hashes), bool)
    keep[np.unique(hashes, return_index=True)[1]] = True
    return keep


def load_flows(csv_path: Path) -> pd.DataFrame:
    """Read a raw flow CSV and clean the known CIC-IDS-2018 defects."""
    keep = _first_occurrence_mask(csv_path)
    numeric = [c for c in USECOLS if c not in ("Timestamp", "Label")]
    frames, seen = [], 0

    # usecols keeps the schema identical across days: some carry 4 extra columns
    # (Flow ID, Src/Dst IP, Src Port). chunksize keeps peak memory flat.
    for chunk in pd.read_csv(csv_path, usecols=USECOLS, chunksize=500_000, low_memory=False):
        rows = len(chunk)
        chunk = chunk[keep[seen:seen + rows]]
        seen += rows
        chunk = chunk[chunk["Label"] != "Label"]  # header rows repeated mid-file

        # "01/03/2018" is day/month/year: 1 March 2018, not 3 January.
        chunk["Timestamp"] = _parse_timestamps(chunk["Timestamp"])
        chunk = chunk[chunk["Timestamp"].notna()]
        chunk[numeric] = chunk[numeric].apply(pd.to_numeric, errors="coerce")
        chunk[numeric] = chunk[numeric].replace([np.inf, -np.inf], np.nan)
        chunk["Label"] = chunk["Label"].astype("category")  # a few names, millions of rows
        frames.append(chunk)

    assert seen == len(keep), f"{csv_path.name}: parsed {seen} rows, hashed {len(keep)}"
    labels = pd.api.types.union_categoricals([c["Label"] for c in frames])
    df = pd.concat([c.drop(columns="Label") for c in frames], ignore_index=True)
    df["Label"] = labels

    # A few rows per day carry corrupt timestamps that parse to 1970. Left in, they
    # stretch the window index over 48 years. Each file is one capture day, so keep
    # the modal date and its neighbours (a capture may cross midnight).
    day = df["Timestamp"].dt.normalize()
    df = df[(day - day.mode()[0]).abs() <= pd.Timedelta("1D")]
    return df.sort_values("Timestamp")


def to_windows(flows: pd.DataFrame) -> pd.DataFrame:
    """Aggregate flows into fixed windows; windows with no flows stay NaN."""
    grouped = flows.groupby(flows["Timestamp"].dt.floor(WINDOW))
    w = grouped.agg(AGG)
    w.columns = [f"{col}_{how}" for col, how in w.columns]
    w["flow_count"] = grouped.size()
    w["attack_flow_count"] = grouped["Label"].apply(lambda s: (s != BENIGN).sum())
    w["attack_types"] = grouped["Label"].apply(lambda s: ",".join(sorted(set(s[s != BENIGN]))))

    # a window with no flows at all is missing data, not quiet traffic
    full = pd.date_range(w.index.min(), w.index.max(), freq=WINDOW, name="window_start")
    assert len(full) <= 8640 * 3, f"{len(full)} windows: timestamps span more than a capture day"
    w = w.reindex(full)
    w["is_gap"] = w["flow_count"].isna()
    w["attack_types"] = w["attack_types"].fillna("")
    w.loc[~w["is_gap"], "Flow Duration_std"] = w.loc[~w["is_gap"], "Flow Duration_std"].fillna(0.0)

    w["bwd_fwd_pkt_ratio"] = w["Tot Bwd Pkts_sum"] / (w["Tot Fwd Pkts_sum"] + 1)
    w["Slice_Attack"] = (w["attack_flow_count"] > 0).astype(float).where(~w["is_gap"])
    return w


def add_history(w: pd.DataFrame, base: list[str]) -> pd.DataFrame:
    """Past-window values and short-term change, so the model can see a trend."""
    history = {f"{c}_lag{k}": w[c].shift(k) for c in base for k in LAGS}
    history |= {f"{c}_delta1": w[c] - w[c].shift(1) for c in base}
    return pd.concat([w, pd.DataFrame(history, index=w.index)], axis=1)


def add_target(w: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Label the FUTURE only: t+1..t+horizon. The current window is excluded."""
    future = pd.concat([w["Slice_Attack"].shift(-k) for k in range(1, horizon + 1)], axis=1)
    # unknown if any future window is a gap or past the end of the capture
    w["Future_Attack_Target"] = future.max(axis=1).where(future.notna().all(axis=1))

    # which attack is coming, for analysis only
    named = w["attack_types"].replace("", np.nan)
    ahead = pd.concat([named.shift(-k) for k in range(1, horizon + 1)], axis=1)
    w["next_attack_type"] = ahead.bfill(axis=1).iloc[:, 0].fillna("")

    onset = (w["Slice_Attack"] == 1) & (w["Slice_Attack"].shift(1) != 1)
    idx = np.arange(len(w))
    next_onset = pd.Series(np.where(onset, idx, np.nan), index=w.index).bfill()
    w["windows_to_next_onset"] = next_onset - idx

    # a window already under attack teaches detection, not forecasting
    w["usable_forecast"] = (
        w["Future_Attack_Target"].notna()
        & ~w["is_gap"]
        & (w["Slice_Attack"] == 0)
        & w[[c for c in w.columns if c.endswith(("_lag1", "_lag2", "_lag3"))]].notna().all(axis=1)
    )
    return w


def build(csv_path: Path, horizon: int = HORIZON) -> pd.DataFrame:
    """One day of raw flows -> one day of labelled windows."""
    w = to_windows(load_flows(csv_path))
    base = [c for c in w.columns if c not in LABEL_COLS]
    return add_target(add_history(w, base), horizon)


def build_many(paths: list[Path], horizon: int = HORIZON) -> pd.DataFrame:
    """Several days, each windowed on its own, concatenated in time order."""
    frames = []
    for p in paths:
        w = build(p, horizon)
        print(f"  {p.name}: {len(w)} windows, {int(w['usable_forecast'].sum())} usable, "
              f"{int(w.loc[w['usable_forecast'], 'Future_Attack_Target'].sum())} positive")
        frames.append(w)
    return pd.concat(frames).sort_index()


def feature_columns(w: pd.DataFrame) -> list[str]:
    """The model's input columns, in training order: no labels, no target."""
    drop = set(LABEL_COLS) | {"usable_forecast", "Future_Attack_Target"}
    return [c for c in w.columns if c not in drop]


def ready_to_train(w: pd.DataFrame) -> pd.DataFrame:
    """Trainable rows only, with every label-derived column already removed."""
    return w[w["usable_forecast"]].drop(columns=LABEL_COLS + ["usable_forecast"])


def sanity(w: pd.DataFrame, ready: pd.DataFrame, horizon: int) -> list[tuple[str, bool, str]]:
    """Every claim the README makes, re-checked against the built frames."""
    feats = ready.drop(columns=["Future_Attack_Target"])
    days = ready.index.normalize()

    # recompute the target straight from the window labels, per day
    recomputed = (
        w.groupby(w.index.normalize())["Slice_Attack"]
        .apply(lambda s: pd.concat([s.shift(-k) for k in range(1, horizon + 1)], axis=1).max(axis=1))
        .droplevel(0)
        .reindex(ready.index)
    )
    return [
        ("chronological order preserved", ready.index.is_monotonic_increasing, str(len(ready))),
        ("no duplicate windows", not ready.index.has_duplicates, ""),
        ("no duplicate rows", not ready.duplicated().any(), ""),
        ("no missing/infinite values", bool(np.isfinite(feats.to_numpy(float)).all()), ""),
        ("no label-derived columns present",
         ready.columns.intersection(LABEL_COLS + ["usable_forecast"]).empty,
         ", ".join(LABEL_COLS)),
        ("target is binary and complete",
         set(ready["Future_Attack_Target"].unique()) <= {0.0, 1.0}, ""),
        ("no row is already under attack (target leads, never detects)",
         bool((w.loc[ready.index, "Slice_Attack"] == 0).all()), ""),
        ("target matches t+1..t+%d recomputed from labels" % horizon,
         bool((recomputed == ready["Future_Attack_Target"]).all()), ""),
        ("every lag is a real preceding window",
         bool((ready["flow_count_lag1"] == w["flow_count"].shift(1).reindex(ready.index)).all()), ""),
        ("both classes present", ready["Future_Attack_Target"].nunique() == 2, ""),
        ("multiple days covered", days.nunique() > 1, f"{days.nunique()} days"),
        ("enough contiguous run for sequence training",
         int(ready.index.to_series().diff().eq(pd.Timedelta(WINDOW)).groupby(
             (~ready.index.to_series().diff().eq(pd.Timedelta(WINDOW))).cumsum()).sum().max()) >= 50,
         "longest unbroken run of consecutive windows"),
    ]


def readme(w: pd.DataFrame, ready: pd.DataFrame, sources: list[Path], horizon: int,
           checks: list[tuple[str, bool, str]], csv_name: str) -> str:
    days = ready.index.normalize()
    pos = ready["Future_Attack_Target"] == 1
    onsets = w[w["windows_to_next_onset"] == 0]
    types = onsets["attack_types"].value_counts()
    per_day = pd.DataFrame({
        "windows": ready.groupby(days).size(),
        "positive": pos.groupby(days).sum(),
        "attacks ahead": ready[pos].groupby(days[pos]).apply(
            lambda g: ", ".join(sorted(set(w.loc[g.index, "next_attack_type"]))) or "-"),
    }).fillna(0)

    lines = [
        f"# {csv_name}", "",
        "Core training set for VectorFlow attack forecasting (SIH PS 26153).",
        f"Generated by `modules/data_pipeline/build_training_set.py --core`.", "",
        "## Source data", "",
        "CSE-CIC-IDS2018 (Communications Security Establishment + Canadian Institute for",
        "Cybersecurity, UNB). Synthetic enterprise traffic captured on an AWS testbed and",
        "reduced to flow records by CICFlowMeter. Public, research-licensed, no real user data.", "",
        "Day files used:", "",
        *[f"- `{p.name}`" for p in sources], "",
        "## What one row is", "",
        f"One {WINDOW} window of aggregated network traffic. `Future_Attack_Target` is 1 when an",
        f"attack appears in the NEXT {horizon} windows (t+1..t+{horizon}, i.e. the following",
        f"{horizon * 10} seconds). The current window is deliberately excluded from the target:",
        "a row where the attack is already running would teach detection, not forecasting.", "",
        "## Preprocessing", "",
        "1. Repeated header rows dropped (CIC files re-emit the header mid-file).",
        "2. Exact duplicate flow rows dropped.",
        "3. `Timestamp` parsed day-first (`01/03/2018` = 1 March), rows with unparseable times dropped.",
        "4. `inf`/`-inf` coerced to NaN; all feature columns forced numeric.",
        "5. Flows floored to their window and aggregated (sum / mean / std / nunique).",
        f"6. Lags {LAGS} (past 10s/20s/30s) and 1-step deltas added per base feature.",
        "7. Windows with zero flows marked as missing data, NOT as quiet traffic. Any window",
        "   whose forecast horizon touches a gap or the end of capture gets an undefined target.",
        "8. Rows dropped unless: target defined, window itself not a gap, window not already",
        "   under attack, and all three lags present.",
        "9. All label-derived columns removed from the exported file.", "",
        "Each day is windowed independently, so no lag, delta or target crosses a day boundary.", "",
        "## Shape", "",
        f"- Rows (windows): {len(ready):,}",
        f"- Feature columns: {ready.shape[1] - 1}",
        f"- Target column: `Future_Attack_Target`",
        f"- Window size: {WINDOW}    Forecast horizon: {horizon} windows ({horizon * 10}s)",
        f"- Days covered: {days.nunique()}",
        f"- Time range: {ready.index.min()} to {ready.index.max()}",
        f"- Windows built before filtering: {len(w):,} (gaps {int(w['is_gap'].sum()):,}, "
        f"already under attack {int((w['Slice_Attack'] == 1).sum()):,})", "",
        "## Label distribution", "",
        f"- 0 (no attack in next {horizon * 10}s): {int((~pos).sum()):,}",
        f"- 1 (attack starts within {horizon * 10}s): {int(pos.sum()):,}"
        f"  ({pos.mean() * 100:.3f}%)",
        f"- Independent attack onsets behind those positives: {len(onsets):,}", "",
        "Left imbalanced on purpose: resampling would destroy the temporal distribution.",
        "Use class weights / `scale_pos_weight`, and judge with PR-AUC or recall at a fixed",
        "alert budget. Accuracy is meaningless here (all-zeros scores ~99.9%).", "",
        "## Attack types at onset", "",
        *[f"- {k or '(unlabelled)'}: {v}" for k, v in types.items()], "",
        "## Per day", "", per_day.to_string(), "",
        "## Feature list", "",
        *[f"{i}. `{c}`" for i, c in enumerate(ready.columns)], "",
        "## Sanity checks", "",
        *[f"- [{'x' if ok else ' '}] {name}" + (f" — {d}" if d else "") for name, ok, d in checks], "",
        "## Assumptions and limits", "",
        "- Attack types are collapsed to one binary target. `next_attack_type` is kept in the",
        "  companion `*_windows.parquet` if per-type modelling is wanted later.",
        "- Sequence models must not run across discontinuities. Rows are chronological but not",
        "  contiguous (gaps and attack windows are removed). Split a sequence wherever",
        "  `window_start.diff() != 10s`.",
        "- Split train/validation BY DAY, never randomly: the three rows before one onset are",
        "  10 seconds apart and nearly identical, so a random split leaks them across the split.",
        "- Ground truth is CIC's own labelling, which is known to be imperfect, and the",
        "  infiltration days in particular are widely reported as weak signal.",
        "- Traffic is synthetic. A model tuned on it needs revalidation on real captures.",
        "- SOURCE FILES ARE TRUNCATED. Seven of the nine day CSVs are exactly 1,048,576 lines",
        "  (2^20, the Excel row limit): the dataset authors saved them through Excel and the",
        "  rest of each day was cut off. Where an attack produced a huge burst of flows early,",
        "  it consumed the whole row budget and most of that day is simply absent. 16-02 keeps",
        "  only 500 of 4,308 windows and contributes NO usable rows; 21-02 keeps 637 and",
        "  contributes only positives. This cannot be recovered from the CSVs - it would need",
        "  re-running CICFlowMeter over the ~220 GB of original PCAPs.",
    ]
    return "\n".join(lines) + "\n"


def _self_check() -> None:
    """Synthetic two-day run: attack at windows 100-102, capture gap at window 150."""
    N, ATTACK, GAP = 200, slice(100, 103), 150

    def day(start: str, scale: float = 1.0) -> pd.DataFrame:
        idx = pd.date_range(start, periods=N, freq=WINDOW, name="window_start")
        d = pd.DataFrame(index=idx)
        d["flow_count"] = (np.arange(N, dtype=float) + 1.0) * scale  # vary: rows stay distinct
        d["is_gap"] = False
        d.loc[idx[GAP], ["flow_count", "is_gap"]] = [np.nan, True]
        d["Slice_Attack"] = 0.0
        d["attack_flow_count"] = 0.0
        d["attack_types"] = ""
        d.loc[idx[ATTACK], ["Slice_Attack", "attack_flow_count"]] = 1.0
        d.loc[idx[ATTACK], "attack_types"] = "Bot"
        d.loc[idx[GAP], "Slice_Attack"] = np.nan
        return add_target(add_history(d, ["flow_count"]), horizon=3)

    w = day("2018-03-01")
    idx, t = w.index, w["Future_Attack_Target"]
    assert list(t[idx[97:100]]) == [1.0, 1.0, 1.0], "3 windows before onset must be positive"
    assert t[idx[96]] == 0.0, "4 windows out is beyond the horizon"
    assert t[idx[99]] == 1.0 and w["Slice_Attack"][idx[99]] == 0.0, "target must lead the attack"
    assert t[idx[147:150]].isna().all(), "windows whose horizon touches the gap are unknown"
    assert not w["usable_forecast"][idx[GAP]], "the gap window itself is never a training row"
    assert t[idx[N - 3:]].isna().all(), "tail windows have no future to look at"
    assert not w["usable_forecast"][idx[ATTACK]].any(), "windows under attack are not forecasting rows"
    assert w["usable_forecast"][idx[98:100]].all(), "clean lead-up windows are usable"
    assert w["windows_to_next_onset"][idx[98]] == 2
    assert w["next_attack_type"][idx[99]] == "Bot" and w["next_attack_type"][idx[0]] == ""

    r = ready_to_train(w)
    assert r.columns.intersection(LABEL_COLS + ["usable_forecast"]).empty, "label columns leaked"
    assert "Future_Attack_Target" in r.columns and r["Future_Attack_Target"].notna().all()
    assert len(r) == int(w["usable_forecast"].sum())

    # two days concatenated: nothing may reach across the boundary
    two = pd.concat([day("2018-03-01"), day("2018-03-02", scale=1.7)]).sort_index()
    assert np.isnan(two["Future_Attack_Target"].iloc[N - 1]), "day-1 tail must stay undefined"
    assert np.isnan(two["flow_count_lag1"].iloc[N]), "day-2 first window must have no lag"
    failed = [n for n, ok, _ in sanity(two, ready_to_train(two), 3) if not ok]
    assert not failed, f"sanity checks failed: {failed}"
    _check_raw_csv_cleaning()

    assert feature_columns(w) + ["Future_Attack_Target"] == list(ready_to_train(w).columns), \
        "feature_columns() and ready_to_train() disagree on the model's input columns"

    from modules.data_pipeline import _check_process_parity
    _check_process_parity()
    print("self-check ok")


def _check_raw_csv_cleaning() -> None:
    """The raw-CSV defences, on a file carrying every defect the real days have."""
    import tempfile

    def row(ts: str, label: str, duration: str = "100") -> str:
        v = dict.fromkeys(USECOLS, "1")
        v["Timestamp"], v["Label"], v["Flow Duration"] = ts, label, duration
        return ",".join(v[c] for c in USECOLS)

    good = [row(f"01/03/2018 00:00:0{i}", BENIGN) for i in range(5)]
    text = "\n".join([
        ",".join(USECOLS),
        *good,
        good[0],                                        # exact duplicate row
        ",".join(USECOLS),                              # header repeated mid-file
        row("01/03/2018 00:00:05", "Bot", "inf"),       # infinite value
        row("01/01/1970 00:00:01", BENIGN),             # corrupt timestamp
    ]) + "\n"

    with tempfile.TemporaryDirectory() as d:
        p = Path(d, "day.csv")
        p.write_text(text)
        df = load_flows(p)

    assert len(df) == 6, f"expected 5 benign + 1 bot, got {len(df)}"
    assert df["Timestamp"].dt.year.eq(2018).all(), "corrupt 1970 timestamp survived"
    assert df["Timestamp"].min() == pd.Timestamp("2018-03-01 00:00:00"), "day-first parsing broke"
    assert df["Flow Duration"].isna().sum() == 1, "inf was not coerced to NaN"
    assert (df["Label"] != BENIGN).sum() == 1, "attack label lost"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("csv", nargs="*", type=Path)
    p.add_argument("-o", "--out", type=Path)
    p.add_argument("--horizon", type=int, default=HORIZON)
    p.add_argument("--ready", action="store_true",
                   help="write only trainable rows, label-derived columns dropped")
    p.add_argument("--core", action="store_true",
                   help="multi-day: write the core training CSV, its README and a windows parquet")
    p.add_argument("--self-check", action="store_true")
    a = p.parse_args()

    if a.self_check:
        return _self_check()
    if not a.csv:
        p.error("csv path(s) required (or --self-check)")

    w = build_many(a.csv, a.horizon)
    print(f"{len(w)} windows, gap {int(w['is_gap'].sum())}, "
          f"under attack {int((w['Slice_Attack'] == 1).sum())}, "
          f"usable {int(w['usable_forecast'].sum())}, "
          f"positives {int(w.loc[w['usable_forecast'], 'Future_Attack_Target'].sum())}")

    if not a.core:
        suffix = "_train" if a.ready else "_windows"
        out = a.out or a.csv[0].with_name(f"{a.csv[0].stem}{suffix}.parquet")
        (ready_to_train(w) if a.ready else w).to_parquet(out)
        return print(f"wrote {out}")

    ready = ready_to_train(w)
    out = a.out or Path("data/cic_ids2018_core_training_dataset.csv")
    checks = sanity(w, ready, a.horizon)
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))

    w.to_parquet(out.with_name(out.stem.replace("training_dataset", "windows") + ".parquet"))
    ready.to_csv(out)
    out.with_suffix(".README.md").write_text(readme(w, ready, a.csv, a.horizon, checks, out.name))
    print(f"wrote {out}: {len(ready)} rows x {ready.shape[1]} columns")
    if not all(ok for _, ok, _ in checks):
        raise SystemExit("SANITY CHECKS FAILED - do not ship this file")


if __name__ == "__main__":
    main()
