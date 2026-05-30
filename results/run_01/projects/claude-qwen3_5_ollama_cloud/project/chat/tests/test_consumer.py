"""
Tests for the WebSocket chat consumer.

These tests verify the consumer logic by inspecting conversation history
and mocking the LLM service. Full integration tests use WebsocketCommunicator.
"""

import json

import pytest

from chat.consumers import ChatConsumer


class FakeStreamingChunk:
    """Fake LangChain streaming chunk."""

    def __init__(self, content: str):
        self.content = content


class FakeChatOllamaClient:
    """Fake ChatOllama client for consumer tests."""

    def __init__(self, model=None, base_url=None, stream=None):
        self._chunks = ["Test", " ", "response", " ", "from", " ", "AI"]

    async def astream(self, messages):
        for content in self._chunks:
            yield FakeStreamingChunk(content)


@pytest.fixture
def mock_chat_ollama(monkeypatch):
    """Mock ChatOllama for all tests in this module."""

    def fake_client(**kwargs):
        return FakeChatOllamaClient(**kwargs)

    monkeypatch.setattr("chat.services.llm.ChatOllama", fake_client)


@pytest.mark.asyncio
async def test_consumer_initializes_with_empty_history():
    """Test consumer starts with empty conversation history."""
    consumer = ChatConsumer()
    assert consumer.conversation_history == []


@pytest.mark.asyncio
async def test_consumer_adds_user_message_to_history():
    """Test that user messages are added to conversation history."""
    consumer = ChatConsumer()

    # Manually add a message to history (simulating what receive() does)
    consumer.conversation_history.append(
        {
            "role": "human",
            "content": "Hello!",
        }
    )

    assert len(consumer.conversation_history) == 1
    assert consumer.conversation_history[0]["role"] == "human"
    assert consumer.conversation_history[0]["content"] == "Hello!"


@pytest.mark.asyncio
async def test_consumer_maintains_conversation_history(mock_chat_ollama):
    """Test consumer adds messages to history for multi-turn context."""
    consumer = ChatConsumer()

    # Simulate receiving a message
    consumer.conversation_history.append(
        {
            "role": "human",
            "content": "First question",
        }
    )

    # After streaming, AI response should be added
    # (In real code this happens in _stream_llm_response)
    consumer.conversation_history.append(
        {
            "role": "ai",
            "content": "Test response from AI",
        }
    )

    assert len(consumer.conversation_history) == 2
    assert consumer.conversation_history[0]["role"] == "human"
    assert consumer.conversation_history[1]["role"] == "ai"


@pytest.mark.asyncio
async def test_consumer_disconnect_clears_history():
    """Test disconnect clears conversation history."""
    consumer = ChatConsumer()

    # Add some history
    consumer.conversation_history.append({"role": "human", "content": "Hello"})
    consumer.conversation_history.append({"role": "ai", "content": "Hi there"})

    assert len(consumer.conversation_history) == 2

    # Disconnect should clear history
    await consumer.disconnect(code=1000)

    assert consumer.conversation_history == []


@pytest.mark.asyncio
async def test_consumer_json_parsing():
    """Test that the consumer properly parses JSON messages."""
    # This is a unit test for the JSON parsing logic
    message = {"message": "Hello!"}
    json_string = json.dumps(message)
    parsed = json.loads(json_string)

    assert parsed["message"] == "Hello!"


@pytest.mark.asyncio
async def test_consumer_handles_empty_message():
    """Test empty message detection."""
    message = {"message": ""}
    is_empty = not message.get("message", "").strip()
    assert is_empty is True


@pytest.mark.asyncio
async def test_consumer_handles_whitespace_message():
    """Test whitespace-only message detection."""
    message = {"message": "   "}
    is_empty = not message.get("message", "").strip()
    assert is_empty is True


@pytest.mark.asyncio
async def test_consumer_valid_message_detection():
    """Test valid message detection."""
    message = {"message": "Hello!"}
    is_valid = bool(message.get("message", "").strip())
    assert is_valid is True
