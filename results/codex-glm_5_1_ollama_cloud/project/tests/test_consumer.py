"""Tests for the ChatConsumer — WebSocket streaming with mocked LLM."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from channels.testing import WebsocketCommunicator


class FakeStream:
    """Yields predictable tokens for assertion."""

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens

    async def __aiter__(self) -> AsyncIterator[str]:
        for tok in self._tokens:
            yield tok


def _mock_stream_factory(tokens: list[str]) -> MagicMock:
    """Return a mock stream_response that yields the given tokens."""
    mock = AsyncMock()
    mock.return_value = FakeStream(tokens)
    return mock


@pytest.fixture()
def communicator() -> WebsocketCommunicator:
    from config.asgi import application

    comm = WebsocketCommunicator(application, "/ws/chat/")
    return comm


class TestChatConsumer:
    @pytest.mark.asyncio
    async def test_connect(self, communicator: WebsocketCommunicator) -> None:
        connected, _ = await communicator.connect()
        assert connected
        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up(self, communicator: WebsocketCommunicator) -> None:
        await communicator.connect()
        await communicator.disconnect()

    @pytest.mark.asyncio
    @patch("chat.consumers.stream_response")
    async def test_streaming_tokens(
        self,
        mock_stream: AsyncMock,
        communicator: WebsocketCommunicator,
    ) -> None:
        mock_stream.return_value = FakeStream(["Hello", " world"])

        await communicator.connect()

        await communicator.send_to(text_data=json.dumps({"message": "hi"}))

        messages = []
        for _ in range(4):
            raw = await communicator.receive_output(timeout=2)
            if raw and "text" in raw:
                msg = json.loads(raw["text"])
                messages.append(msg)

        types = [m["type"] for m in messages]
        assert "start" in types
        assert "end" in types

        token_messages = [m for m in messages if m["type"] == "token"]
        assert len(token_messages) == 2
        assert token_messages[0]["content"] == "Hello"
        assert token_messages[1]["content"] == " world"

        await communicator.disconnect()

    @pytest.mark.asyncio
    @patch("chat.consumers.stream_response")
    async def test_stream_error(
        self,
        mock_stream: AsyncMock,
        communicator: WebsocketCommunicator,
    ) -> None:
        mock_stream.side_effect = RuntimeError("ollama down")

        await communicator.connect()

        await communicator.send_to(text_data=json.dumps({"message": "hi"}))

        messages = []
        for _ in range(3):
            raw = await communicator.receive_output(timeout=2)
            if raw and "text" in raw:
                msg = json.loads(raw["text"])
                messages.append(msg)

        types = [m["type"] for m in messages]
        assert "start" in types
        assert "error" in types

        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_invalid_json(self, communicator: WebsocketCommunicator) -> None:
        await communicator.connect()

        await communicator.send_to(text_data="not-json")

        raw = await communicator.receive_output(timeout=2)
        msg = json.loads(raw["text"])
        assert msg["type"] == "error"

        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_empty_message(self, communicator: WebsocketCommunicator) -> None:
        await communicator.connect()

        await communicator.send_to(text_data=json.dumps({"message": ""}))

        raw = await communicator.receive_output(timeout=2)
        msg = json.loads(raw["text"])
        assert msg["type"] == "error"

        await communicator.disconnect()

    @pytest.mark.asyncio
    @patch("chat.consumers.stream_response")
    async def test_multi_turn_conversation(
        self,
        mock_stream: AsyncMock,
        communicator: WebsocketCommunicator,
    ) -> None:
        mock_stream.return_value = FakeStream(["reply"])

        await communicator.connect()

        # First turn
        await communicator.send_to(text_data=json.dumps({"message": "hello"}))
        for _ in range(3):
            await communicator.receive_output(timeout=2)

        # Second turn — reset mock for new FakeStream
        mock_stream.return_value = FakeStream(["second reply"])
        await communicator.send_to(text_data=json.dumps({"message": "follow up"}))
        for _ in range(3):
            await communicator.receive_output(timeout=2)

        # Verify stream_response was called twice (multi-turn)
        assert mock_stream.call_count == 2
        # Second call includes history: human, ai, human
        second_call_args = mock_stream.call_args[0][0]
        assert second_call_args[0]["role"] == "human"
        assert second_call_args[1]["role"] == "ai"
        assert second_call_args[2]["role"] == "human"

        await communicator.disconnect()
