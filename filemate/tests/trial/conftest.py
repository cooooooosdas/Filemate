"""Reuse the existing original synthetic learning world."""

import pytest

from filemate.tests.orchestrator.conftest import world  # noqa: F401


@pytest.fixture(autouse=True)
def trial_enabled(monkeypatch):
    monkeypatch.setenv("FILEMATE_ENABLE_TRIAL_WORKSPACE", "1")
