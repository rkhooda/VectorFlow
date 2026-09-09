"""Module entry points the orchestrator calls: mock or real, chosen in config.yaml.

`modules.<module>.implementation: mock | real` selects each module independently
(docs/integration.md). Modules without a real implementation yet stay mocked.
"""

from backend.app.core.config import get_config
from backend.app.services import mocks
from modules import attack_intelligence, data_pipeline, forecasting


def _pick(modules: dict, name: str, real, mock):
    """The real module when config.yaml asks for it, else the mock stand-in."""
    return real if modules.get(name, {}).get("implementation") == "real" else mock


_modules = get_config()["modules"]

process = _pick(_modules, "data_pipeline", data_pipeline.process, mocks.process)
forecast = _pick(_modules, "forecasting", forecasting.forecast, mocks.forecast)
analyze = _pick(_modules, "attack_intelligence", attack_intelligence.analyze, mocks.analyze)
