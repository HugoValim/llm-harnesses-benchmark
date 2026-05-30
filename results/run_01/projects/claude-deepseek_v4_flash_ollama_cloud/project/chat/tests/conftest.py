from collections.abc import AsyncIterator

import pytest
from langchain_core.messages import AIMessageChunk


class FakeChatOllama:
    """Fake LLM client that yields predefined chunks for testing."""

    def __init__(self, chunks: list[str] | None = None):
        self.chunks = chunks or ['Hello', ' ', 'world', '!']

    async def astream(self, messages) -> AsyncIterator[AIMessageChunk]:
        for chunk in self.chunks:
            yield AIMessageChunk(content=chunk)


class FailingChatOllama:
    """Fake LLM client that raises on stream."""

    async def astream(self, messages) -> AsyncIterator[AIMessageChunk]:
        raise ConnectionError('Connection refused')
        yield  # pragma: no cover — makes this an async generator


@pytest.fixture
def fake_ollama_chunks():
    return ['Hello', ' ', 'from', ' ', 'Ollama', '!']


@pytest.fixture
def fake_ollama():
    return FakeChatOllama()


@pytest.fixture
def failing_ollama():
    return FailingChatOllama()
