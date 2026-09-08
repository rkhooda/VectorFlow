# ML Forecasting Module — VectorFlow
**SIH 2026 | PS 26153: AI-based Network Attack Forecasting from Network Traffic Data**

This module learns past network behaviour from time-based network states and forecasts future attack probability over a forecast horizon (predicting whether an attack initiates within 120 seconds) using the **CIC-IDS2018** benchmark dataset.

---

## Architecture & Integration Contract

In accordance with `docs/integration.md`, this module implements the contract interface:
```python
def forecast(states: list[NetworkState], config: dict) -> ForecastResult:
    ...
```

- **In-process execution**: Loaded directly by `backend/app/services/`.
- **Strict typing**: Exchanges typed Pydantic models from `contracts/` (`NetworkState`, `ForecastResult`, `ForecastPoint`).
- **Lazy initialization**: Artifacts (`scaler.joblib` and `xgboost.ubj`) are loaded lazily on the first call to `forecast()`, avoiding startup crashes and memory overhead during application bootstrap.
- **Strict feature validation**: Validates that all 75 engineered traffic features are present in incoming `NetworkState` objects without silent default fallbacks.
- **Horizon projection**: The `horizon` list currently extrapolates future probabilities with dynamic window duration spacing (default 10s per window). This serves as a baseline extrapolation placeholder until autoregressive sequence models (LSTM / Transformer) are trained for multi-step forecasting.

---

## Setup & Dependencies

### 1. Requirements

Backend inference dependencies are included in the root `requirements.txt`:
- `scikit-learn==1.4.2`
- `xgboost==2.0.3`
- `joblib==1.4.0`

> [!NOTE]
> **macOS Requirement**: XGBoost requires OpenMP runtime. If running on macOS, install OpenMP via Homebrew:
> ```bash
> brew install libomp
> ```

Optional development and UI demo dependencies (`streamlit`, `matplotlib`, `python-dotenv`) are listed in `modules/forecasting/requirements.txt`:
```bash
pip install -r modules/forecasting/requirements.txt
```

### 2. Model Weights & Regeneration

Model binaries are deliberately excluded from git tracking (`.gitignore`) to keep the repository lightweight. To generate the model artifacts locally:

```bash
python modules/forecasting/run.py
```
This trains Logistic Regression, Random Forest, and XGBoost on the chronological training split and exports the following artifacts to `modules/forecasting/models/`:
- `scaler.joblib` (StandardScaler fitted on training features)
- `xgboost.ubj` (Primary production XGBoost classifier)
- `randomforest.joblib` (Random Forest classifier)
- `logreg.joblib` (Logistic Regression baseline)

### 3. Interactive Web Demo (Streamlit)

Launch the standalone Streamlit exploration interface:
```bash
streamlit run modules/forecasting/app.py
```

---

## Dataset & Preprocessing

- **Dataset**: CIC-IDS2018
- **Dimensions**: 17,356 rows × 75 engineered traffic features (+ timestamp + target)
- **Aggregation**: 10-second traffic windows
- **Target Definition**: `Future_Attack_Target = 1` if an attack starts within the next 120 seconds

### Chronological Split (No Data Leakage)

- **Train**: Feb 14, Feb 15, Feb 22, Feb 23
- **Validation**: Feb 28
- **Test**: Mar 01, Mar 02

> **Known Exclusions**:
> - `2018-02-21`: Excluded (contains only 61 rows, 100% positive, truncated artifact).
> - `2018-02-16`: Confirmed absent in raw source.

---

## Model Benchmark

Benchmark numbers are pending. The tables previously listed here were not
produced from `data/cic_ids2018_core_training_dataset.csv`, so they were
removed. Regenerate them with `python modules/forecasting/run.py` on that file
and paste the printed comparison table and confusion matrices here, including
the March 01–02 test split. Early runs rank test-day windows near chance and
the 0.15 alert threshold fires on roughly a quarter of all windows, so the
backend keeps the mock forecaster until this improves.

---

## Directory Layout

```
modules/forecasting/
├── __init__.py          # Contract entry point: forecast(states, config) -> ForecastResult
├── inference.py         # Lazy model loading, feature validation, and prediction API
├── app.py               # Interactive Streamlit demo
├── run.py               # Model training, split evaluation, and metrics generation
├── requirements.txt     # Demo and training dependencies (Streamlit, Matplotlib, etc.)
├── README.md            # Module documentation and benchmark report
├── models/              # Gitignored local model artifacts (scaler, xgb, rf, lr)
└── src/                 # Internal modules
    ├── __init__.py
    ├── data.py          # Data ingestion, audit, and temporal train/val/test splitting
    ├── model.py         # Model builders (LogisticRegression, RandomForest, XGBoost)
    ├── evaluate.py      # Metrics computation (ROC-AUC, PR-AUC, Confusion Matrix)
    ├── plots.py         # Feature importance and PR-curve visualization
    └── persist.py       # Model serialization / deserialization helpers
```
