"""Module entry points the orchestrator calls: mock or real, chosen in config.yaml.

`modules.<module>.implementation: mock | real` selects each module independently
(docs/integration.md). Modules without a real implementation yet stay mocked.
"""

from backend.app.core.config import get_config
from backend.app.services import mocks
from modules import attack_intelligence, data_pipeline

_modules = get_config()["modules"]

process = (
    data_pipeline.process
    if _modules.get("data_pipeline", {}).get("implementation") == "real"
    else mocks.process
)
forecast = mocks.forecast
analyze = (
    attack_intelligence.analyze
    if _modules.get("attack_intelligence", {}).get("implementation") == "real"
    else mocks.analyze
)
