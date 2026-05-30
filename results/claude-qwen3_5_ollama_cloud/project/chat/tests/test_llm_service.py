"""
Tests for the LLM service module.
"""

import os

import pytest

from chat.services.llm import LLMService, get_llm_service


class FakeStreamingChunk:
    """Fake LangChain streaming chunk for tests."""

    def __init__(self, content: str):
        self.content = content


class FakeChatOllamaClient:
    """
    Fake ChatOllama client for testing.

    Simulates streaming behavior with multiple chunks.
    """

    def __init__(self, model: str = None, base_url: str = None, stream: bool = None):
        self.model = model
        self.base_url = base_url
        self.stream = stream
        self._response_chunks = [
            "Hello",
            " ",
            "there",
            "!",
            " ",
            "How",
            " ",
            "can",
            " ",
            "I",
            " ",
            "help",
            "?",
        ]

    async def astream(self, messages):
        """Fake streaming response - yields chunks with delays."""
        for chunk_content in self._response_chunks:
            yield FakeStreamingChunk(chunk_content)


class FakeFailingChatOllamaClient:
    """Fake client that raises connection errors."""

    def __init__(self, *args, **kwargs):
        pass

    async def astream(self, messages):
        """Async generator that raises a connection error."""
        if True:  # Always raise on first iteration
            raise ConnectionError("Connection refused to Ollama server")
        yield  # Never reached - makes this an async generator


@pytest.fixture
def llm_service():
    """Create an LLM service instance with test configuration."""
    return LLMService(host="http://localhost:11434", model="test-model")


@pytest.fixture
def mock_chat_ollama(monkeypatch):
    """Mock the ChatOllama import to use our fake client."""

    def fake_chat_ollama(**kwargs):
        return FakeChatOllamaClient(**kwargs)

    monkeypatch.setattr("chat.services.llm.ChatOllama", fake_chat_ollama)


@pytest.mark.asyncio
async def test_llm_service_initialization():
    """Test LLM service uses environment variables correctly."""
    service = LLMService()
    assert service.host == os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    assert service.model == os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


@pytest.mark.asyncio
async def test_llm_service_custom_config():
    """Test LLM service accepts custom host and model."""
    service = LLMService(host="http://custom:11434", model="custom-model")
    assert service.host == "http://custom:11434"
    assert service.model == "custom-model"


@pytest.mark.asyncio
async def test_llm_service_streams_tokens(llm_service, mock_chat_ollama):
    """
    Test that the LLM service streams tokens one at a time.

    Verifies multiple chunks are yielded separately, not just the final result.
    """
    messages = [{"role": "human", "content": "Hello!"}]
    tokens = []

    async for token in llm_service.stream_response(messages):
        tokens.append(token)

    # Verify we got multiple streamed chunks
    assert len(tokens) > 1
    assert tokens == [
        "Hello",
        " ",
        "there",
        "!",
        " ",
        "How",
        " ",
        "can",
        " ",
        "I",
        " ",
        "help",
        "?",
    ]


@pytest.mark.asyncio
async def test_llm_service_connection_error(llm_service, monkeypatch):
    """Test that connection errors are properly surfaced."""

    def fake_failing_client(**kwargs):
        return FakeFailingChatOllamaClient(**kwargs)

    monkeypatch.setattr("chat.services.llm.ChatOllama", fake_failing_client)

    messages = [{"role": "human", "content": "Hello!"}]

    # The service wraps connection errors with a descriptive message
    with pytest.raises(ConnectionError) as exc_info:
        async for _ in llm_service.stream_response(messages):
            pass

    # Check error contains helpful info about Ollama
    assert "Ollama" in str(exc_info.value)


@pytest.mark.asyncio
async def test_llm_service_health_check_healthy(llm_service, mock_chat_ollama):
    """Test health check returns healthy status when Ollama is reachable."""
    result = await llm_service.health_check()

    assert result["healthy"] is True
    assert result["host"] == "http://localhost:11434"
    assert result["model"] == "test-model"
    assert "error" not in result


@pytest.mark.asyncio
async def test_llm_service_health_check_unhealthy(llm_service, monkeypatch):
    """Test health check reports unhealthy when Ollama is unreachable."""

    def fake_failing_client(**kwargs):
        return FakeFailingChatOllamaClient(**kwargs)

    monkeypatch.setattr("chat.services.llm.ChatOllama", fake_failing_client)

    result = await llm_service.health_check()

    assert result["healthy"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_get_llm_service_singleton():
    """Test that get_llm_service returns a singleton instance."""
    service1 = get_llm_service()
    service2 = get_llm_service()
    assert service1 is service2


@pytest.mark.asyncio
async def test_llm_service_conversation_context(llm_service, mock_chat_ollama):
    """Test that conversation history is properly formatted for LangChain."""
    messages = [
        {"role": "human", "content": "First message"},
        {"role": "ai", "content": "First response"},
        {"role": "human", "content": "Second message"},
    ]

    # Just verify it doesn't raise - the fake client accepts any messages
    tokens = []
    async for token in llm_service.stream_response(messages):
        tokens.append(token)

    assert len(tokens) > 0
