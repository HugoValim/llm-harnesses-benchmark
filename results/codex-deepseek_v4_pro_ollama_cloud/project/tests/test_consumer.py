"""Tests for ChatConsumer using Channels WebsocketCommunicator."""

from unittest.mock import patch

import pytest
from channels.testing import WebsocketCommunicator

from chat.consumers import ChatConsumer
from chat.services import LLMError


async def _fake_stream(_messages):
    for token in ["Hello", " from", " Ollama"]:
        yield token


class TestChatConsumer:
    """Consumer receives text, streams LLM tokens back."""

    @pytest.fixture
    async def communicator(self) -> WebsocketCommunicator:
        comm = WebsocketCommunicator(ChatConsumer.as_asgi(), "/ws/chat/")
        connected, _ = await comm.connect()
        assert connected
        return comm

    @pytest.mark.asyncio
    async def test_connect_disconnect(self) -> None:
        comm = WebsocketCommunicator(ChatConsumer.as_asgi(), "/ws/chat/")
        connected, _ = await comm.connect()
        assert connected
        await comm.disconnect()

    @pytest.mark.asyncio
    async def test_streams_multiple_chunks(self, communicator: WebsocketCommunicator) -> None:
        with patch("chat.consumers.stream_chat", side_effect=_fake_stream):
            await communicator.send_to(text_data="Hello, world!")

            responses = []
            for _ in range(3):
                resp = await communicator.receive_from()
                responses.append(resp)

            assert responses == ["Hello", " from", " Ollama"]

        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_handles_llm_error(self, communicator: WebsocketCommunicator) -> None:
        async def _raise(*_args, **_kw):
            raise LLMError("Ollama is offline")
            yield  # unreachable, makes it an async generator

        with patch("chat.consumers.stream_chat", side_effect=_raise):
            await communicator.send_to(text_data="ping")

            resp = await communicator.receive_from()
            assert "Ollama is offline" in resp

        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_empty_message_ignored(self, communicator: WebsocketCommunicator) -> None:
        with patch("chat.consumers.stream_chat") as mock_stream:
            await communicator.send_to(text_data="   ")
            mock_stream.assert_not_called()

        await communicator.disconnect()
