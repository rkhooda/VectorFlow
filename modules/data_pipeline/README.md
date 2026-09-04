# Data Pipeline module

Owner: Data Pipeline teammate.

Turns raw PCAP/CSV input into cleaned, feature-extracted, time-windowed
network states.

Implement the contract described in `docs/integration.md` using the Pydantic
models from `contracts/`. The backend imports this package in-process; a mock
in `backend/app/services/` stands in until this module is ready.

## Training-set builder

`build_training_set.py` turns a raw CIC-IDS-2018 flow CSV into 10-second
windows with lag features and a leak-free forecasting target:

```
python -m modules.data_pipeline.build_training_set data/03-01-2018.csv          # _windows.parquet, all 4320 windows
python -m modules.data_pipeline.build_training_set data/03-01-2018.csv --ready  # _train.parquet, trainable rows only
python -m modules.data_pipeline.build_training_set --self-check
```

`--ready` is what goes to the ML owner: trainable rows only, every
label-derived column already removed, so `Future_Attack_Target` is the target
and every other column is a feature.

Train only on rows where `usable_forecast` is true — those exclude windows
already under attack, capture gaps, and windows whose lags or horizon are
incomplete. `Slice_Attack` is the current-window label: keep it out of the
feature set, it is what `Future_Attack_Target` is derived from.

### Multi-day core dataset

```
python -m modules.data_pipeline.build_training_set data/raw/*.csv data/03-01-2018.csv \
    --core --horizon 12 -o data/cic_ids2018_core_training_dataset.csv
```

`--core` writes the training CSV, a generated README beside it, and a
`*_windows.parquet` keeping the label columns for analysis and dashboard
replay. Each day is windowed independently, so no lag, delta or target ever
crosses a capture boundary. `--horizon` is in windows: 12 = 2 minutes.

Sanity checks run on every `--core` build and the command exits non-zero if
any fails, so a bad dataset cannot be written silently.

## Runtime: `process()`

```python
from modules.data_pipeline import process
states = process(Path("capture.csv"))   # -> list[NetworkState]
```

`process()` does **not** reimplement the feature engineering. It calls the same
`load_flows()`, `to_windows()` and `add_history()` used to build the training
file, and orders columns with the same `feature_columns()`. A model trained on
the core dataset therefore receives exactly the columns it was trained on.

Do not hand-write a second copy of this feature logic. `--self-check` asserts
that `process()` reproduces the training rows with a maximum difference of
`0.0`; that guarantee only holds while there is one implementation.

`process()` returns more windows than the training file contains: windows that
were already under attack, or whose forecast horizon was undefined, are dropped
from *training* but are perfectly valid to *predict on*. Windows with an
incomplete feature vector (capture gaps, and the first windows of a capture,
which have no history to lag from) are excluded.

`NetworkState.flows` is empty. The CIC-IDS-2018 day files carry no Flow ID,
source IP, destination IP or source port, so per-flow records cannot be
honestly reconstructed from them; `flow_count`, `packet_count` and
`byte_count` are exact. Populating `FlaggedFlow` for the dashboard needs a
capture that has those columns.
