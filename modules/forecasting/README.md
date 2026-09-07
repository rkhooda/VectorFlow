# ML Forecasting Module — VectorFlow
**SIH 2026 | PS 26153: AI-based Network Attack Forecasting from Network Traffic Data**

This module learns past network behaviour from time-based network states and forecasts future network attack probability over a forecast horizon (predicting whether an attack initiates within 120 seconds) using the **CIC-IDS2018** benchmark dataset.

---

## Architecture & Integration

In accordance with `docs/integration.md`, this module implements the contract interface:
```python
def forecast(states: list[NetworkState], config: dict) -> ForecastResult:
    ...
```

- **In-process execution**: Seamlessly loaded by `backend/app/services/`
- **Strict typing**: Exchanges typed Pydantic models from `contracts/` (`NetworkState`, `ForecastResult`, `ForecastPoint`)
- **Offline & reproducible**: Bundles trained model weights and scalers inside `models/`

---

## Quick Start

### 1. Requirements

Install module dependencies:
```bash
pip install -r requirements.txt
```

### 2. Standalone Model Training & Evaluation

Train Logistic Regression, Random Forest, and XGBoost classifiers, evaluate on chronological splits, and export feature importance:
```bash
python run.py
```

### 3. Interactive Web Demo (Streamlit)

Launch the interactive UI for manual traffic feature experimentation and batch CSV evaluation:
```bash
streamlit run app.py
```

---

## Dataset & Preprocessing

- **Dataset**: CIC-IDS2018
- **Dimensions**: 17,356 rows × 75 engineered traffic features (+ timestamp + target)
- **Aggregation**: 10-second traffic windows
- **Target Variable**: `Future_Attack_Target = 1` if an attack starts within the subsequent 120 seconds

### Chronological Split (No Random Leakage)

| Split | Included Dates | Rows | Positives |
|---|---|---|---|
| **Train** | Feb 14, Feb 15, Feb 22, Feb 23 | 11,296 | ~8-9% |
| **Validation** | Feb 28 | 2,526 | Shifted distribution |
| **Test** | Mar 01, Mar 02 | 3,473 | Shifted distribution |

> **Notes on Exclusions**:
> - `2018-02-21` is excluded (contains only 61 rows, all positive, Excel truncation artifact).
> - `2018-02-16` contributes 0 rows (confirmed absent in raw source).

---

## Model Zoo & Key Findings

Three core architectures are trained and evaluated:
1. **Logistic Regression** (L2 regularized, balanced class weighting)
2. **Random Forest** (400 estimators, min samples leaf = 4, balanced)
3. **XGBoost** (400 estimators, depth = 6, scale_pos_weight dynamic balancing)

### Key Empirical Findings
- **Distribution Shift**: Due to temporal distribution shift between training days and evaluation days, models exhibit $F_1 = 0$ at the fixed 0.5 default decision threshold.
- **Strong Ranking Signal**: Validation ROC-AUC of **~0.73** (Random Forest) and **~0.74** (XGBoost) demonstrates strong discriminatory ranking power.
- **Top Discriminative Features**:
  1. `RST Flag Cnt_sum` (and corresponding lags)
  2. `Flow IAT Mean_mean` (and corresponding lags)
  3. `Dst Port_nunique` (destination port entropy / spread)

---

## Directory Structure

```
modules/forecasting/
├── __init__.py          # Contract entry point: forecast(states, config) -> ForecastResult
├── inference.py         # Model loading, validation, and multi-model prediction pipeline
├── app.py               # Streamlit demo dashboard
├── run.py               # Training and evaluation runner
├── requirements.txt     # Module dependencies
├── README.md            # Module documentation
├── models/              # Pretrained model artifacts
│   ├── scaler.joblib
│   ├── logreg.joblib
│   ├── randomforest.joblib
│   └── xgboost.ubj
└── src/                 # Implementation utilities
    ├── data.py          # Data ingestion, audit, and temporal splitting
    ├── model.py         # Model definitions and hyperparameter setup
    ├── evaluate.py      # Metrics computation and confusion matrices
    ├── plots.py         # Feature importance and PR-curve visualization
    └── persist.py       # Model serialization
```
