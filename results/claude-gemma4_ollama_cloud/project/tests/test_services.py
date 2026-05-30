from typing import Any, AsyncGenerator
from unittest.mock import MagicMock

import pytest

from chat.services import LLMService


@pytest.mark.asyncio
async def test_llm_service_streaming() -> None:
    service = LLMService()

    # Mock the ChatOllama astream method
    mock_llm = MagicMock()

    async def mock_astream(messages: Any) -> AsyncGenerator[MagicMock, None]:
        yield MagicMock(content="Hello")
        yield MagicMock(content=" world")
        yield MagicMock(content="!")

    mock_llm.astream = mock_astream
    service.llm = mock_llm

    messages = [{"role": "user", "content": "Hi"}]
    results = []
    async for chunk in service.stream_chat(messages):
        results.append(chunk)

    assert results == ["Hello", " world", "!"]


@pytest.mark.asyncio
async def test_llm_service_error() -> None:
    service = LLMService()

    mock_llm = MagicMock()

    async def mock_astream(messages: Any) -> AsyncGenerator[None, None]:
        # To simulate an error in an async generator, we just raise inside the gen
        raise Exception("Ollama connection failed")
        yield  # This makes it a generator

    mock_llm.astream = mock_astream
    service.llm = mock_llm

    messages = [{"role": "user", "content": "Hi"}]
    results = []
    async for chunk in service.stream_chat(messages):
        results.append(chunk)

    assert "Error: Ollama connection failed" in results[0]
