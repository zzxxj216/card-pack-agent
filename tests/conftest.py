"""Pytest fixtures and config."""
from __future__ import annotations

import os

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "smoke: fast structural tests (mock mode, no network)")
    config.addinivalue_line("markers", "integration: requires real API + services")


@pytest.fixture(scope="session", autouse=True)
def force_mock_mode():
    """Smoke tests must never hit real APIs. Force mock mode at session start."""
    os.environ["APP_MODE"] = "mock"
    # Force re-read of settings
    from card_pack_agent import config
    config.settings.app_mode = config.AppMode.MOCK
    yield
