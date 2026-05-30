"""
Tests for WebSocket consumer.
"""

import json
from unittest.mock import patch

import pytest
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator

from chat.routing import websocket_urlpatterns


class FakeLLMService:
    """Fake LLM service for consumer testing."""

    def __init__(self) -> None:
        self.history_cleared = False

    async def stream_response(self, message: str, system_prompt: str | None = None):
        """Fake streaming response."""
        chunks = ["Test", " ", "response"]
        for chunk in chunks:
            yield chunk

    async def health_check(self) -> bool:
        """Fake health check."""
        return True

    def clear_history(self) -> None:
        """Track history clear."""
        self.history_cleared = True


class FakeLLMServiceError:
    """Fake LLM service that raises error."""

    def __init__(self) -> None:
        self.history_cleared = False

    async def stream_response(self, message: str, system_prompt: str | None = None):
        """Simulate error."""
        raise ConnectionError("Ollama unreachable")
        if False:
            yield None

    async def health_check(self) -> bool:
        """Fake health check."""
        return False

    def clear_history(self) -> None:
        """Track history clear."""
        self.history_cleared = True


@pytest.mark.asyncio
async def test_consumer_connect() -> None:
    """Test WebSocket connection."""
    with patch("chat.consumers.LLMService", FakeLLMService):
        application = URLRouter(websocket_urlpatterns)
        communicator = WebsocketCommunicator(application, "/ws/chat/")
        connected, _ = await communicator.connect()

        assert connected is True

        response = await communicator.receive_json_from()
        assert response["type"] == "connected"

        await communicator.disconnect()


@pytest.mark.asyncio
async def test_consumer_receive_message_streams() -> None:
    """Test that consumer streams tokens from LLM."""
    with patch("chat.consumers.LLMService", FakeLLMService):
        application = URLRouter(websocket_urlpatterns)
        communicator = WebsocketCommunicator(application, "/ws/chat/")
        connected, _ = await communicator.connect()

        # Consume connected message
        await communicator.receive_json_from()

        await communicator.send_to(text_data=json.dumps({"message": "Hello"}))

        token_responses = []
        while True:
            response = await communicator.receive_json_from()
            if response["type"] == "complete":
                break
            if response["type"] == "token":
                token_responses.append(response)

        assert len(token_responses) == 3
        assert token_responses[0]["type"] == "token"
        assert token_responses[0]["content"] == "Test"
        assert token_responses[1]["content"] == " "
        assert token_responses[2]["content"] == "response"

        complete_response = response
        assert complete_response["type"] == "complete"
        assert complete_response["content"] == "Test response"

        await communicator.disconnect()


@pytest.mark.asyncio
async def test_consumer_handles_error() -> None:
    """Test that consumer handles LLM errors gracefully."""
    with patch("chat.consumers.LLMService", FakeLLMServiceError):
        application = URLRouter(websocket_urlpatterns)
        communicator = WebsocketCommunicator(application, "/ws/chat/")
        connected, _ = await communicator.connect()

        # Consume connected message
        await communicator.receive_json_from()

        await communicator.send_to(text_data=json.dumps({"message": "Hello"}))

        response = await communicator.receive_json_from()
        assert response["type"] == "error"
        assert "Ollama unreachable" in response["message"]

        await communicator.disconnect()


@pytest.mark.asyncio
async def test_consumer_rejects_invalid_json() -> None:
    """Test that consumer rejects invalid JSON."""
    with patch("chat.consumers.LLMService", FakeLLMService):
        application = URLRouter(websocket_urlpatterns)
        communicator = WebsocketCommunicator(application, "/ws/chat/")
        connected, _ = await communicator.connect()

        # Consume connected message
        await communicator.receive_json_from()

        await communicator.send_to(text_data="not json")

        response = await communicator.receive_json_from()
        assert response["type"] == "error"
        assert response["message"] == "Invalid JSON"

        await communicator.disconnect()


@pytest.mark.asyncio
async def test_consumer_rejects_empty_message() -> None:
    """Test that consumer rejects empty messages."""
    with patch("chat.consumers.LLMService", FakeLLMService):
        application = URLRouter(websocket_urlpatterns)
        communicator = WebsocketCommunicator(application, "/ws/chat/")
        connected, _ = await communicator.connect()

        # Consume connected message
        await communicator.receive_json_from()

        await communicator.send_to(text_data=json.dumps({"message": ""}))

        response = await communicator.receive_json_from()
        assert response["type"] == "error"
        assert response["message"] == "Empty message"

        await communicator.disconnect()


@pytest.mark.asyncio
async def test_consumer_disconnect_clears_history() -> None:
    """Test that disconnect clears conversation history."""
    fake_service = FakeLLMService()
    with patch("chat.consumers.LLMService", return_value=fake_service):
        application = URLRouter(websocket_urlpatterns)
        communicator = WebsocketCommunicator(application, "/ws/chat/")
        connected, _ = await communicator.connect()

        await communicator.disconnect()

        assert fake_service.history_cleared is True
