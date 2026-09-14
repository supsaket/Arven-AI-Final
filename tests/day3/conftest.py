"""Day 3 shared fixtures (hermetic: everything uses tmp_path stores)."""

import pytest

from core.confirmation import CONFIRMATION
from tools.builder import build_registry


@pytest.fixture(scope="session")
def registry():
    return build_registry()


@pytest.fixture(scope="session")
def names(registry):
    return registry.names()


def mint(context="day3.test.action"):
    """Open a real pending CONFIRMATION request (consumed by registry gates)."""
    return CONFIRMATION.require(context)