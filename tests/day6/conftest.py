"""Day 6 shared fixtures: feature 123 mechatronics engine."""

import pytest

from core.mechatronics import MechatronicsEngine
from tools.builder import build_registry


@pytest.fixture()
def engine(tmp_path):
    return MechatronicsEngine(kv_path=str(tmp_path / "mech.json"),
                              out_dir=str(tmp_path / "out"))


@pytest.fixture(scope="session")
def registry():
    return build_registry()


@pytest.fixture(scope="session")
def names(registry):
    return registry.names()