"""
Canonical Inference API for VectorFlow LSTM forecasting.
"""

import os
from typing import Dict, Any, Union, List, Optional
import numpy as np
import pandas as pd
import torch

try:  # package import for the backend; fallback keeps the CLI/tests working
    from .features import BASE_FEATURES
    from .utils import load_json, load_artifact
except ImportError:  # pragma: no cover - exercised by the standalone CLI
    from features import BASE_FEATURES
    from utils import load_json, load_artifact


class InsufficientHistoryError(ValueError):
    """Raised when replay has not collected a full causal LSTM sequence."""

FEATURE_COLS = BASE_FEATURES


class InferencePipeline:
    """
    Production-ready inference wrapper for VectorFlow LSTM Attack Forecaster.
    """
    def __init__(self, artifacts_dir: str = "lstm/artifacts"):
        self.artifacts_dir = artifacts_dir
        self.scaler = None
        self.model = None
        self.threshold = 0.5
        self.feature_cols = BASE_FEATURES
        self.sequence_length = 6
        self.config = {}
        self.is_loaded = False

    def load_artifacts(self):
        """Lazily load trained model, scaler, and threshold metadata."""
        if self.is_loaded:
            return

        scaler_path = os.path.join(self.artifacts_dir, "scaler.joblib")
        model_path = os.path.join(self.artifacts_dir, "lstm_model.pt")
        meta_path = os.path.join(self.artifacts_dir, "model_metadata.json")

        if not os.path.exists(scaler_path) or not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Missing required model artifacts in '{self.artifacts_dir}'. "
                "Please run training pipeline first."
            )

        self.scaler = load_artifact(scaler_path)

        if os.path.exists(meta_path):
            meta = load_json(meta_path)
            self.threshold = float(meta.get("threshold", 0.5))
            self.feature_cols = meta.get("feature_cols", BASE_FEATURES)
            self.sequence_length = int(meta.get("sequence_length", 6))
            self.config = meta

        # Load PyTorch model
        try:
            from .model import AttackLSTM
        except ImportError:  # pragma: no cover - standalone CLI
            from model import AttackLSTM
        input_dim = len(self.feature_cols)
        hidden_size = self.config.get("hidden_size", 64)
        num_layers = self.config.get("num_layers", 1)

        self.model = AttackLSTM(
            input_dim=input_dim,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=0.0,
        )

        state_dict = torch.load(model_path, map_location="cpu")
        self.model.load_state_dict(state_dict)
        self.model.eval()
        self.is_loaded = True

    def predict_sequence(
        self,
        sequence: Union[np.ndarray, pd.DataFrame, List[Dict[str, float]]],
        custom_threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Accepts real historical sequence of past sequence_length 10-second windows.

        Input formats:
        - 3D numpy array [1, S, F] or 2D numpy array [S, F]
        - pandas DataFrame with S rows containing feature_cols
        - list of S feature dicts
        """
        if isinstance(sequence, pd.DataFrame):
            missing = [c for c in self.feature_cols if c not in sequence.columns]
            if missing:
                raise ValueError(f"Input sequence DataFrame missing required features: {missing}")
            raw_data = sequence[self.feature_cols].values.astype(np.float32)
        elif isinstance(sequence, list):
            df_seq = pd.DataFrame(sequence)
            missing = [c for c in self.feature_cols if c not in df_seq.columns]
            if missing:
                raise ValueError(f"Input sequence dict list missing required features: {missing}")
            raw_data = df_seq[self.feature_cols].values.astype(np.float32)
        elif isinstance(sequence, np.ndarray):
            if sequence.ndim == 3:
                raw_data = sequence[0].astype(np.float32)
            elif sequence.ndim == 2:
                raw_data = sequence.astype(np.float32)
            else:
                raise ValueError(f"Invalid numpy sequence dimensions: {sequence.ndim}")
        else:
            raise TypeError(f"Unsupported sequence input type: {type(sequence)}")

        # Never pad a causal history: repeated rows would manufacture context
        # and make an early replay prediction look more certain than it is.
        if len(raw_data) < self.sequence_length:
            raise InsufficientHistoryError(
                f"Collecting historical context ({len(raw_data)}/{self.sequence_length} windows)"
            )
        if len(raw_data) > self.sequence_length:
            # Take the most recent sequence_length windows
            raw_data = raw_data[-self.sequence_length :]

        self.load_artifacts()

        # Scale sequence features [1, S, F] using frozen scaler
        S, F = raw_data.shape
        scaled_data = self.scaler.transform(raw_data).reshape(1, S, F).astype(np.float32)

        # Inference forward pass
        with torch.no_grad():
            tensor_in = torch.from_numpy(scaled_data)
            proba = float(self.model.predict_proba(tensor_in)[0].item())

        thresh = custom_threshold if custom_threshold is not None else self.threshold
        pred = int(proba >= thresh)

        return {
            "attack_probability": round(proba, 4),
            "prediction": pred,
            "threshold": round(thresh, 4),
            "forecast_horizon_seconds": {
                "min": 30,
                "max": 60,
            },
            "sequence_length": self.sequence_length,
            "feature_count": F,
        }


# Module singleton for convenience
_pipeline = None


def get_inference_pipeline(artifacts_dir: str = "lstm/artifacts") -> InferencePipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = InferencePipeline(artifacts_dir=artifacts_dir)
    return _pipeline


def predict_sequence(
    sequence: Union[np.ndarray, pd.DataFrame, List[Dict[str, float]]],
    artifacts_dir: str = "lstm/artifacts",
) -> Dict[str, Any]:
    pipeline = get_inference_pipeline(artifacts_dir=artifacts_dir)
    return pipeline.predict_sequence(sequence)


predict = predict_sequence
