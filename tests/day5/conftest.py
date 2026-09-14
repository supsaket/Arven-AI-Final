"""Day 5 shared fixtures: features 112-122 all-name terminal acceptance."""

import pytest

from tools.builder import build_registry


@pytest.fixture(scope="session")
def registry():
    return build_registry()


@pytest.fixture(scope="session")
def names(registry):
    return registry.names()