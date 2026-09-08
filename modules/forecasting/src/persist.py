"""
persist.py - save and load trained models and the scaler
"""

import os
import joblib


def save(models: dict, scaler, model_dir: str = "models"):
    """
    Save all models and the scaler to model_dir.

    - LogReg, RandomForest  → joblib (.joblib)
    - XGBoost               → native binary format (.ubj) via save_model()
    - StandardScaler        → joblib (.joblib)
    """
    os.makedirs(model_dir, exist_ok=True)

    scaler_path = os.path.join(model_dir, "scaler.joblib")
    joblib.dump(scaler, scaler_path)
    print(f"Saved scaler  → {scaler_path}")

    for name, model in models.items():
        if name == "XGBoost":
            path = os.path.join(model_dir, "xgboost.ubj")
            model.save_model(path)
        else:
            filename = name.lower().replace(" ", "_") + ".joblib"
            path = os.path.join(model_dir, filename)
            joblib.dump(model, path)

        print(f"Saved {name:<14} → {path}")


def load(model_dir: str = "models"):
    """
    Load scaler and all models from model_dir.
    Returns (scaler, models_dict).
    """
    from xgboost import XGBClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import RandomForestClassifier

    scaler = joblib.load(os.path.join(model_dir, "scaler.joblib"))

    xgb = XGBClassifier()
    xgb.load_model(os.path.join(model_dir, "xgboost.ubj"))

    models = {
        "LogReg":       joblib.load(os.path.join(model_dir, "logreg.joblib")),
        "RandomForest": joblib.load(os.path.join(model_dir, "randomforest.joblib")),
        "XGBoost":      xgb,
    }

    return scaler, models
