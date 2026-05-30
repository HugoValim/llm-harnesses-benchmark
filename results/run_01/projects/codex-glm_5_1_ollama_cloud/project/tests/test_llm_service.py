"""Tests for the LLM service module — mocked LangChain/Ollama path."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from chat.services.llm import (
    OLLAMA_HOST_DEFAULT,
    OLLAMA_MODEL_DEFAULT,
    _ollama_host,
    _ollama_model,
    stream_response,
)


class TestConfig:
    def test_ollama_host_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("OLLAMA_HOST", None)
            assert _ollama_host() == OLLAMA_HOST_DEFAULT

    def test_ollama_host_env_override(self) -> None:
        with patch.dict(os.environ, {"OLLAMA_HOST": "http://custom:11434"}):
            assert _ollama_host() == "http://custom:11434"

    def test_ollama_model_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("OLLAMA_MODEL", None)
            assert _ollama_model() == OLLAMA_MODEL_DEFAULT

    def test_ollama_model_env_override(self) -> None:
        with patch.dict(os.environ, {"OLLAMA_MODEL": "llama3:8b"}):
            assert _ollama_model() == "llama3:8b"


class FakeAsyncStream:
    """Async iterator yielding predictable AIMessage-like chunks."""

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self._index = 0

    def __aiter__(self) -> FakeAsyncStream:
        return self

    async def __anext__(self) -> MagicMock:
        if self._index >= len(self._tokens):
            raise StopAsyncIteration
        token = self._tokens[self._index]
        self._index += 1
        chunk = MagicMock()
        chunk.content = token
        return chunk


def _make_mock_client(tokens: list[str]) -> MagicMock:
    """Create a mock ChatOllama client whose astream() returns a FakeAsyncStream."""
    mock_client = MagicMock()
    mock_client.astream = MagicMock(return_value=FakeAsyncStream(tokens))
    return mock_client


class TestStreamResponse:
    @pytest.mark.asyncio
    async def test_yields_tokens_from_llm(self) -> None:
        mock_client = _make_mock_client(["Hello", " world"])

        with patch("chat.services.llm.get_llm_client", return_value=mock_client):
            messages = [{"role": "human", "content": "hi"}]
            tokens = []
            async for token in stream_response(messages):
                tokens.append(token)

        assert tokens == ["Hello", " world"]

    @pytest.mark.asyncio
    async def test_unknown_role_raises(self) -> None:
        messages = [{"role": "system", "content": "you are helpful"}]
        with pytest.raises(ValueError, match="Unknown role"):
            async for _ in stream_response(messages):
                pass

    @pytest.mark.asyncio
    async def test_empty_content_skipped(self) -> None:
        mock_client = _make_mock_client(["", "yes"])

        with patch("chat.services.llm.get_llm_client", return_value=mock_client):
            tokens = []
            async for token in stream_response([{"role": "human", "content": "go"}]):
                tokens.append(token)

        assert tokens == ["yes"]
