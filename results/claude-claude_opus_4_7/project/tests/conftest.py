"""Shared fixtures for the test suite.

Environment setup (secret key, allowed hosts) lives in the root ``conftest.py``
so it runs before Django is configured. This module holds reusable fixtures.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from chat import consumers
from tests.fakes import FakeChatService


@pytest.fixture
def fake_service() -> FakeChatService:
    """A scripted fake LLM service with multiple streamed tokens."""
    return FakeChatService(tokens=["Hel", "lo", " wor", "ld"])


@pytest.fixture
def patched_service(
    monkeypatch: pytest.MonkeyPatch, fake_service: FakeChatService
) -> Iterator[FakeChatService]:
    """Patch the consumer's service factory to return the fake service."""
    monkeypatch.setattr(consumers, "create_chat_service", lambda: fake_service)
    yield fake_service
