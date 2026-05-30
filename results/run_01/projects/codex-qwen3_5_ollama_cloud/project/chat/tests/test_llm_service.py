"""
Tests for LLM service module.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from chat.llm_service import LLMService


class FakeChatOllama:
    """Fake ChatOllama client for testing."""

    def __init__(self, model: str, base_url: str) -> None:
        self.model = model
        self.base_url = base_url

    async def astream(self, messages: list):
        """Fake streaming response."""
        chunks = ["Hello", " ", "world", "!"]
        for chunk in chunks:
            mock_chunk = MagicMock()
            mock_chunk.content = chunk
            yield mock_chunk


class FakeChatOllamaError:
    """Fake ChatOllama that raises an error."""

    def __init__(self, model: str, base_url: str) -> None:
        self.model = model
        self.base_url = base_url

    async def astream(self, messages: list):
        """Simulate connection error."""
        raise ConnectionError("Ollama not reachable")
        if False:
            yield None


@pytest.mark.asyncio
async def test_llm_service_streams_chunks() -> None:
    """Test that LLM service streams multiple chunks."""
    with patch("chat.llm_service.ChatOllama", FakeChatOllama):
        service = LLMService()
        tokens = []
        async for token in service.stream_response("test message"):
            tokens.append(token)

        assert tokens == ["Hello", " ", "world", "!"]


@pytest.mark.asyncio
async def test_llm_service_updates_history() -> None:
    """Test that conversation history is updated after response."""
    with patch("chat.llm_service.ChatOllama", FakeChatOllama):
        service = LLMService()
        async for _ in service.stream_response("test message"):
            pass

        assert len(service.conversation_history) == 1
        assert service.conversation_history[0]["role"] == "user"
        assert service.conversation_history[0]["content"] == "test message"


@pytest.mark.asyncio
async def test_llm_service_clear_history() -> None:
    """Test that clear_history removes all messages."""
    with patch("chat.llm_service.ChatOllama", FakeChatOllama):
        service = LLMService()
        async for _ in service.stream_response("test"):
            pass

        service.clear_history()
        assert len(service.conversation_history) == 0


@pytest.mark.asyncio
async def test_llm_service_health_check_success() -> None:
    """Test health check returns True when Ollama is reachable."""
    with patch("chat.llm_service.ChatOllama", FakeChatOllama):
        service = LLMService()
        result = await service.health_check()
        assert result is True


@pytest.mark.asyncio
async def test_llm_service_health_check_failure() -> None:
    """Test health check returns False when Ollama is unreachable."""
    with patch("chat.llm_service.ChatOllama", FakeChatOllamaError):
        service = LLMService()
        result = await service.health_check()
        assert result is False


@pytest.mark.asyncio
async def test_llm_service_connection_error() -> None:
    """Test that connection error is raised when Ollama fails."""
    with patch("chat.llm_service.ChatOllama", FakeChatOllamaError):
        service = LLMService()
        with pytest.raises(ConnectionError, match="Failed to stream"):
            async for _ in service.stream_response("test"):
                pass


def test_llm_service_uses_env_vars() -> None:
    """Test that LLM service reads from environment variables."""
    original_host = os.environ.get("OLLAMA_HOST")
    original_model = os.environ.get("OLLAMA_MODEL")

    try:
        os.environ["OLLAMA_HOST"] = "http://custom-host:11434"
        os.environ["OLLAMA_MODEL"] = "custom-model:latest"

        service = LLMService()

        assert service.client.model == "custom-model:latest"
        assert service.client.base_url == "http://custom-host:11434"
    finally:
        if original_host:
            os.environ["OLLAMA_HOST"] = original_host
        if original_model:
            os.environ["OLLAMA_MODEL"] = original_model
