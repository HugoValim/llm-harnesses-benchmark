"""Fake LLM streamer for tests."""

from collections.abc import AsyncIterator
from typing import Any


class FakeLlmStreamer:
    """Yield fixed tokens for testing."""

    tokens = ["Hello", ", ", "world", "!"]

    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        pass

    async def astream(self, messages: list[dict[str, Any]]) -> AsyncIterator[str]:
        for token in self.tokens:
            yield token
