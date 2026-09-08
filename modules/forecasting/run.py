"""
run.py - VectorFlow entry point for ML model training and evaluation
Usage:  python modules/forecasting/run.py
"""

import warnings
warnings.filterwarnings("ignore")

import os
import sys

# Ensure local src/ is on sys.path for standalone script execution
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = os.path.join(_MODULE_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from sklearn.preprocessing import StandardScaler

import data as D
import model as M
import evaluate as E
import plots as P
import persist as Persist

DATA_PATH  = os.getenv("DATA_PATH",  "data/cic_ids2018_core_training_dataset.csv")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", os.path.join(_MODULE_DIR, "outputs"))
MODEL_DIR  = os.getenv("MODEL_DIR",  os.path.join(_MODULE_DIR, "models"))

OUT_FI = os.path.join(OUTPUT_DIR, "feature_importance.png")
OUT_PR = os.path.join(OUTPUT_DIR, "pr_curves.png")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

if not os.path.exists(DATA_PATH):
    print(f"Error: Dataset not found at '{DATA_PATH}'.")
    print("Please set DATA_PATH env var or place the CIC-IDS2018 dataset at the expected path.")
    sys.exit(1)

df = D.load(DATA_PATH)
print(f"Loaded {len(df):,} rows, {df.shape[1]} columns")
print(f"Date range: {df['window_start'].min()} → {df['window_start'].max()}")

D.audit(df)

train_df, val_df, test_df = D.split(df)

feat_cols = D.feature_cols(df)
X_train, y_train = D.xy(train_df, feat_cols)
X_val,   y_val   = D.xy(val_df,   feat_cols)
X_test,  y_test  = D.xy(test_df,  feat_cols)

print(f"\nFeature matrix — train: {X_train.shape}, val: {X_val.shape}, test: {X_test.shape}")

scaler = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
X_val_s   = scaler.transform(X_val)
X_test_s  = scaler.transform(X_test)

trained_models = M.train_all(X_train_s, y_train)

Persist.save(trained_models, scaler, MODEL_DIR)

splits = {
    "train": (X_train_s, y_train),
    "val":   (X_val_s,   y_val),
    "test":  (X_test_s,  y_test),
}

results = E.evaluate_all(trained_models, splits)
E.print_comparison(results)

P.print_feature_importance(trained_models, feat_cols)

P.plot_feature_importance(trained_models, feat_cols, OUT_FI)
P.plot_pr_curves(trained_models, splits, OUT_PR)
