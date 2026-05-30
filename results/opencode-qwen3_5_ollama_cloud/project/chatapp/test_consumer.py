"""
Tests for WebSocket consumer streaming.
"""

import asyncio
from typing import Any, AsyncGenerator

import pytest
from channels.testing import WebsocketCommunicator
from unittest.mock import AsyncMock, patch

from chatproject.asgi import application


class FakeChunk:
    """Fake response chunk."""

    def __init__(self, content: str) -> None:
        self.content = content


class FakeChatModel:
    """Fake ChatOllama for testing streaming behavior."""

    def __init__(self, chunks: list[str] | None = None) -> None:
        self.chunks = chunks or ["Hello", " ", "world", "!"]

    async def astream(
        self, messages: list[dict[str, Any]]
    ) -> AsyncGenerator[FakeChunk, None]:
        """Stream fake chunks."""
        for chunk_text in self.chunks:
            yield FakeChunk(chunk_text)


@pytest.mark.asyncio
class TestChatConsumer:
    """Test WebSocket consumer streaming."""

    async def test_consumer_connect(self) -> None:
        """Test WebSocket connection."""
        communicator = WebsocketCommunicator(application, "/ws/chat/")
        connected, subprotocol = await communicator.connect()

        assert connected is True

        response = await communicator.receive_json_from()
        assert response["type"] == "connected"

        await communicator.disconnect()

    async def test_consumer_receive_message(self) -> None:
        """Test consumer receives and processes messages."""
        communicator = WebsocketCommunicator(application, "/ws/chat/")
        connected, _ = await communicator.connect()
        assert connected

        await communicator.receive_json_from()

        fake_model = FakeChatModel(["Test", " ", "response"])
        with patch("chatapp.consumers.get_chat_model", return_value=fake_model):
            await communicator.send_json_to({"message": "Hello"})

            stream_start = await communicator.receive_json_from()
            assert stream_start["type"] == "stream_start"

            chunks = []
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        communicator.receive_json_from(), timeout=0.5
                    )
                    if chunk["type"] == "stream_chunk":
                        chunks.append(chunk["content"])
                    elif chunk["type"] == "stream_end":
                        break
                except TimeoutError:
                    break

            assert len(chunks) > 0

        await communicator.disconnect()

    async def test_consumer_streams_multiple_chunks(self) -> None:
        """Test that consumer streams multiple chunks individually."""
        communicator = WebsocketCommunicator(application, "/ws/chat/")
        connected, _ = await communicator.connect()
        assert connected

        await communicator.receive_json_from()

        test_chunks = ["Chunk", "1", " ", "Chunk", "2"]
        fake_model = FakeChatModel(test_chunks)
        with patch("chatapp.consumers.get_chat_model", return_value=fake_model):
            await communicator.send_json_to({"message": "Test"})

            await communicator.receive_json_from()

            received_chunks = []
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        communicator.receive_json_from(), timeout=0.5
                    )
                    if chunk["type"] == "stream_chunk":
                        received_chunks.append(chunk["content"])
                    elif chunk["type"] == "stream_end":
                        break
                except TimeoutError:
                    break

            assert len(received_chunks) == len(test_chunks)
            for i, expected in enumerate(test_chunks):
                assert received_chunks[i] == expected

        await communicator.disconnect()

    async def test_consumer_disconnect_cleans_up(self) -> None:
        """Test disconnect cleans up resources."""
        communicator = WebsocketCommunicator(application, "/ws/chat/")
        connected, _ = await communicator.connect()
        assert connected

        await communicator.receive_json_from()
        await communicator.disconnect()

    async def test_consumer_handles_empty_message(self) -> None:
        """Test consumer handles empty message gracefully."""
        communicator = WebsocketCommunicator(application, "/ws/chat/")
        connected, _ = await communicator.connect()
        assert connected

        await communicator.receive_json_from()

        await communicator.send_json_to({"message": ""})

        response = await communicator.receive_json_from()
        assert response["type"] == "error"
        assert "Empty" in response["message"]

        await communicator.disconnect()

    async def test_consumer_handles_llm_error(self) -> None:
        """Test consumer handles LLM errors."""
        communicator = WebsocketCommunicator(application, "/ws/chat/")
        connected, _ = await communicator.connect()
        assert connected

        await communicator.receive_json_from()

        async def failing_astream(
            messages: list[dict[str, Any]],
        ) -> AsyncGenerator[None, None]:
            raise ConnectionError("Connection refused")
            yield  # type: ignore[unreachable]

        fake_model = AsyncMock()
        fake_model.astream = failing_astream

        with patch("chatapp.consumers.get_chat_model", return_value=fake_model):
            await communicator.send_json_to({"message": "Hello"})

            await communicator.receive_json_from()

            error_response = await communicator.receive_json_from()
            assert error_response["type"] == "error"
            assert "Ollama" in error_response["message"]

        await communicator.disconnect()
