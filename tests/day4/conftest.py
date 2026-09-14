"""Day 4 shared fixtures: all-111 terminal acceptance suite."""

import pytest

from tools.builder import build_registry


@pytest.fixture(scope="session")
def registry():
    return build_registry()


@pytest.fixture(scope="session")
def names(registry):
    return registry.names()