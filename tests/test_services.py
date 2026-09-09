"""The mock/real switch that decides which module code a session actually runs.

A wrong switch is silent: the demo keeps working and quietly serves mock numbers,
so every module gets an explicit case here.
"""

import yaml

from backend.app.services import _pick

REAL, MOCK = "real-impl", "mock-impl"
MODULES = ("data_pipeline", "forecasting", "attack_intelligence")


def test_real_only_when_config_says_real():
    for name in MODULES:
        assert _pick({name: {"implementation": "real"}}, name, REAL, MOCK) == REAL
        assert _pick({name: {"implementation": "mock"}}, name, REAL, MOCK) == MOCK


def test_mock_when_module_or_key_is_absent():
    for name in MODULES:
        assert _pick({}, name, REAL, MOCK) == MOCK
        assert _pick({name: {}}, name, REAL, MOCK) == MOCK


def test_one_module_does_not_switch_another():
    modules = {"data_pipeline": {"implementation": "real"}}
    assert _pick(modules, "data_pipeline", REAL, MOCK) == REAL
    assert _pick(modules, "forecasting", REAL, MOCK) == MOCK
    assert _pick(modules, "attack_intelligence", REAL, MOCK) == MOCK


def test_config_yaml_declares_every_module():
    """config.yaml must carry a switch for each module, or it silently mocks."""
    with open("config.yaml") as f:
        modules = yaml.safe_load(f)["modules"]
    for name in MODULES:
        assert modules.get(name, {}).get("implementation") in ("mock", "real"), name
