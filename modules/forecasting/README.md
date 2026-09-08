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

Optional development and UI demo dependencies (`streamlit`, `matplotlib`, `seaborn`, `python-dotenv`) are listed in `modules/forecasting/requirements.txt`:
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

| Split | Included Dates | Rows | Positives | Positive Rate |
|---|---|---|---|---|
| **Train** | Feb 14, Feb 15, Feb 22, Feb 23 | 11,296 | ~995 | ~8.8% |
| **Validation** | Feb 28 | 2,526 | 213 | ~8.4% |
| **Test** | Mar 01, Mar 02 | 3,473 | ~38 | ~1.1% |

> **Known Exclusions**:
> - `2018-02-21`: Excluded (contains only 61 rows, 100% positive, truncated artifact).
> - `2018-02-16`: Confirmed absent in raw source.

---

## Model Benchmark & Empirical Findings

### Performance Comparison Across Splits

Due to severe class imbalance and temporal shift, standard accuracy is misleading (a dummy all-negative classifier reaches >98% accuracy on test days while detecting zero attacks). PR-AUC, ROC-AUC, and threshold-calibrated Recall/F1 are the primary metrics.

| Model | Split | ROC-AUC | PR-AUC | Default Threshold (0.5)<br>Precision / Recall / F1 | Tuned Threshold (0.15)<br>Precision / Recall / F1 | Max Prob Observed |
|---|---|---|---|---|---|---|
| **Logistic Regression** | Train<br>Val (Feb 28)<br>Test (Mar 01–02) | 0.81<br>0.64<br>0.52 | 0.28<br>0.12<br>0.01 | 0.15 / 0.72 / 0.25<br>0.00 / 0.00 / 0.00<br>0.00 / 0.00 / 0.00 | 0.18 / 0.65 / 0.28<br>0.10 / 0.42 / 0.16<br>0.02 / 0.35 / 0.04 | 0.89<br>0.48<br>0.24 |
| **Random Forest** | Train<br>Val (Feb 28)<br>Test (Mar 01–02) | 0.99<br>0.73<br>0.55 | 0.94<br>0.24<br>0.01 | 0.92 / 0.86 / 0.89<br>0.00 / 0.00 / 0.00<br>0.00 / 0.00 / 0.00 | 0.65 / 0.96 / 0.77<br>0.18 / 0.54 / 0.27<br>0.03 / 0.40 / 0.06 | 0.96<br>0.49<br>0.20 |
| **XGBoost** | Train<br>Val (Feb 28)<br>Test (Mar 01–02) | 0.98<br>0.74<br>0.57 | 0.91<br>0.27<br>0.02 | 0.88 / 0.81 / 0.84<br>0.00 / 0.00 / 0.00<br>0.00 / 0.00 / 0.00 | 0.58 / 0.92 / 0.71<br>0.21 / 0.56 / 0.31<br>0.04 / 0.42 / 0.07 | 0.95<br>0.52<br>0.25 |

### Analysis of Test Days (March 01 & 02) and Distribution Shift

1. **The 0.5 Threshold Issue**:
   - On evaluation days, the maximum probability assigned across the entire day rarely exceeds `0.20`–`0.25`.
   - At the default `0.5` decision boundary, **all models output zero true positives (Recall = 0, F1 = 0)**.
2. **Temporal Attack Shift**:
   - **Training Days (Feb 14–23)** contain voluminous DoS (HTTP/LOIC) and Brute Force attacks causing drastic spikes in flag counts, flow rates, and packet deltas.
   - **Test Days (Mar 01–02)** represent subtle Infiltration attacks (e.g., internal host compromise via dropbox / Metasploit) where network traffic behaves almost identically to benign background traffic, resulting in low raw probabilities and a test ROC-AUC drop to ~0.55–0.57.
3. **Calibrated Decision Threshold**:
   - By calibrating the decision threshold from the validation precision-recall curve at `threshold = 0.15` (instead of `0.50`), the system recovers practical detection recall (40–56% recall) while alerting downstream analysts.
4. **Top Discriminative Features**:
   - `RST Flag Cnt_sum` (and lags 1–3)
   - `Flow IAT Mean_mean` (and lags 1–3)
   - `Dst Port_nunique` (destination port diversity)
   - `Tot Fwd Pkts_sum_delta1`

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
