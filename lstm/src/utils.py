"""
Utility functions for reproducibility, persistence, and formatting.
"""

import os
import json
import random
import joblib
import numpy as np
import torch


def set_seed(seed: int = 42):
    """Set random seed across Python, NumPy, and PyTorch for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False


def ensure_dir(path: str):
    """Ensure directory exists."""
    os.makedirs(path, exist_ok=True)


def save_json(data: dict, file_path: str):
    """Save dictionary as formatted JSON."""
    ensure_dir(os.path.dirname(file_path))
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def load_json(file_path: str) -> dict:
    """Load JSON file."""
    with open(file_path, "r") as f:
        return json.load(f)


def save_artifact(obj, file_path: str):
    """Save joblib artifact."""
    ensure_dir(os.path.dirname(file_path))
    joblib.dump(obj, file_path)


def load_artifact(file_path: str):
    """Load joblib artifact."""
    return joblib.load(file_path)
