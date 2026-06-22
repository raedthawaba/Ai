"""pytest configuration and shared fixtures for all test suites."""

from __future__ import annotations

import asyncio
import pytest


def pytest_configure(config):
    """إعداد pytest markers."""
    config.addinivalue_line("markers", "asyncio: mark test as async")


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use the default asyncio event loop policy."""
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="session")
def event_loop():
    """Create a single shared event loop for the test session."""
    policy = asyncio.DefaultEventLoopPolicy()
    loop = policy.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()
