"""Loads config.yaml from the repository root."""

from functools import lru_cache
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_FILE = REPO_ROOT / "config.yaml"


@lru_cache(maxsize=1)
def get_config() -> dict:
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)
