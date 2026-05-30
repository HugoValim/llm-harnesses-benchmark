from collections.abc import AsyncIterator
from typing import Any

import pytest

from chat.services import OLLAMA_HOST, OLLAMA_MODEL, ollama_reachable, stream_reply


class FakeOllamaClient:
    """Named fake LLM client that yields multiple chunks."""

    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens

    async def astream(self, messages: Any) -> AsyncIterator[Any]:
        class FakeChunk:
            def __init__(self, text: str) -> None:
                self.content = text

        for tok in self.tokens:
            yield FakeChunk(tok)


def test_env_defaults() -> None:
    assert OLLAMA_HOST == "http://localhost:11434"
    assert OLLAMA_MODEL == "qwen2.5:7b"


def test_ollama_reachable_returns_bool() -> None:
    result = ollama_reachable()
    assert isinstance(result, bool)


@pytest.mark.asyncio
async def test_stream_reply_yields_multiple_chunks(monkeypatch: Any) -> None:
    tokens = ["Hello", " ", "world"]

    def fake_build_client() -> FakeOllamaClient:
        return FakeOllamaClient(tokens)

    monkeypatch.setattr("chat.services.build_client", fake_build_client)

    chunks = []
    async for chunk in stream_reply([{"role": "human", "content": "hi"}]):
        chunks.append(chunk)

    assert len(chunks) == 3
    assert "".join(chunks) == "Hello world"
