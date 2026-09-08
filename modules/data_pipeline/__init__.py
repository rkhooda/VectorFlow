"""Data pipeline: a raw capture file becomes a list of NetworkState windows.

The feature engineering is NOT reimplemented here. `process()` calls the very
same `load_flows()`, `to_windows()` and `add_history()` that built
`data/cic_ids2018_core_training_dataset.csv`, so a model trained on that file
is handed exactly the columns it was trained on, in the same order. Parity is
structural rather than maintained by hand - there is only one implementation.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from contracts import NetworkState

# build_training_set is imported inside the functions, not here: it is also run
# as `python -m modules.data_pipeline.build_training_set`, and importing it at
# package level would load it twice.


def window_span() -> pd.Timedelta:
    """The window length the training set was built with."""
    from .build_training_set import WINDOW

    return pd.Timedelta(WINDOW)


def extract_features(input_path: Path) -> pd.DataFrame:
    """Raw flow CSV -> one row per window, columns exactly as the model expects.

    Windows without a complete feature vector are dropped: a capture gap has no
    traffic to describe, and the first windows of a capture have no history to
    lag from. This is the same rule the training set applies, minus the parts
    that depend on labels (which do not exist at prediction time).
    """
    from .build_training_set import LABEL_COLS, USECOLS, add_history, feature_columns, load_flows, to_windows

    if input_path.suffix.lower() != ".csv":
        raise ValueError("only CIC-IDS-2018 flow CSVs are supported; convert PCAP with CICFlowMeter first")
    with open(input_path, encoding="utf-8", errors="replace") as fh:
        header = {c.strip() for c in fh.readline().split(",")}
    if missing := sorted(set(USECOLS) - header):
        raise ValueError(f"not a CIC-IDS-2018 flow CSV, missing columns: {missing}")

    w = to_windows(load_flows(Path(input_path)))
    w = add_history(w, [c for c in w.columns if c not in LABEL_COLS])
    feats = w[feature_columns(w)]
    return feats[feats.notna().all(axis=1)]


def process(input_path: Path, config: dict | None = None) -> list[NetworkState]:
    """Entry point (docs/integration.md): capture file -> windows for forecasting.

    `flows` is empty: the CIC-IDS-2018 day files carry no Flow ID, source IP,
    destination IP or source port, so per-flow records cannot be honestly
    reconstructed from them. The counts are exact.
    """
    feats = extract_features(input_path)
    span = window_span()

    return [
        NetworkState(
            window_index=i,
            window_start=start.to_pydatetime(),
            window_end=(start + span).to_pydatetime(),
            features={k: float(v) for k, v in row.items()},
            flows=[],
            flow_count=int(row["flow_count"]),
            packet_count=int(row["Tot Fwd Pkts_sum"] + row["Tot Bwd Pkts_sum"]),
            byte_count=int(row["TotLen Fwd Pkts_sum"] + row["TotLen Bwd Pkts_sum"]),
        )
        for i, (start, row) in enumerate(feats.iterrows())
    ]


def _check_process_parity() -> None:
    """process() must emit the training file's columns, in the training order."""
    import tempfile

    from .build_training_set import AGG, BENIGN, USECOLS, build, ready_to_train

    def row(second: int, packets: int) -> str:
        v = dict.fromkeys(USECOLS, "1")
        v["Timestamp"] = f"01/03/2018 00:{second // 60:02d}:{second % 60:02d}"
        v["Label"] = BENIGN
        v["Tot Fwd Pkts"], v["Tot Bwd Pkts"] = str(packets), str(packets * 2)
        v["TotLen Fwd Pkts"], v["TotLen Bwd Pkts"] = str(packets * 10), str(packets * 20)
        return ",".join(v[c] for c in USECOLS)

    text = "\n".join([",".join(USECOLS), *(row(s, s + 1) for s in range(0, 600, 10))]) + "\n"

    with tempfile.TemporaryDirectory() as d:
        p = Path(d, "day.csv")
        p.write_text(text)
        states = process(p)
        trained = ready_to_train(build(p, horizon=3))

    assert states, "process() returned no windows"
    expected = list(trained.columns.drop("Future_Attack_Target"))
    assert list(states[0].features) == expected, (
        "process() features do not match the training columns:\n"
        f"  extra:   {set(states[0].features) - set(expected)}\n"
        f"  missing: {set(expected) - set(states[0].features)}"
    )
    assert len(expected) == 75, f"expected 75 model features, got {len(expected)}"

    # every training row must be reproducible byte-for-byte by process()
    served = pd.DataFrame([s.features for s in states],
                          index=[s.window_start for s in states])
    served.index = pd.DatetimeIndex(served.index)
    shared = trained.index.intersection(served.index)
    assert len(shared) == len(trained), "process() dropped windows the training set kept"
    diff = (trained.loc[shared, expected] - served.loc[shared, expected]).abs().max().max()
    assert diff == 0.0, f"train/serve feature mismatch: max difference {diff}"

    s = states[0]
    assert s.window_end - s.window_start == window_span()
    assert s.packet_count == s.features["Tot Fwd Pkts_sum"] + s.features["Tot Bwd Pkts_sum"]
    assert s.flow_count == int(s.features["flow_count"])
    assert [x.window_index for x in states] == list(range(len(states)))
