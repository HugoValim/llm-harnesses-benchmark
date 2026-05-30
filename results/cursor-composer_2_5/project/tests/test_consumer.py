"""WebSocket consumer streaming tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
from channels.testing import WebsocketCommunicator
from config.asgi import application
from django.test import override_settings


async def _fake_token_stream(
    _history: list,
    _user_text: str,
) -> AsyncIterator[str]:
    for token in ("One", "Two", "Three"):
        yield token


@pytest.mark.asyncio
@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
async def test_chat_consumer_streams_multiple_tokens() -> None:
    communicator = WebsocketCommunicator(application, "/ws/chat/")
    connected, _ = await communicator.connect()
    assert connected

    with patch("chat.consumers.llm.stream_chat_tokens", side_effect=_fake_token_stream):
        await communicator.send_json_to({"message": "Hello"})
        user_html = await communicator.receive_from()
        start_html = await communicator.receive_from()
        token_one = await communicator.receive_from()
        token_two = await communicator.receive_from()
        token_three = await communicator.receive_from()
        end_html = await communicator.receive_from()

    assert "Hello" in user_html
    assert "assistant-" in start_html
    assert "One" in token_one
    assert "Two" in token_two
    assert "Three" in token_three
    assert "hx-swap-oob" in end_html

    await communicator.disconnect()


@pytest.mark.asyncio
@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
async def test_chat_consumer_surfaces_stream_errors() -> None:
    communicator = WebsocketCommunicator(application, "/ws/chat/")
    connected, _ = await communicator.connect()
    assert connected

    async def boom(_history: list, _user_text: str) -> AsyncIterator[str]:
        raise RuntimeError("provider down")
        yield ""  # pragma: no cover

    with patch("chat.consumers.llm.stream_chat_tokens", side_effect=boom):
        await communicator.send_json_to({"message": "Hi"})
        await communicator.receive_from()
        await communicator.receive_from()
        error_html = await communicator.receive_from()

    assert "Streaming failed" in error_html
    await communicator.disconnect()


@pytest.mark.asyncio
@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
async def test_chat_consumer_disconnect_cleans_up() -> None:
    communicator = WebsocketCommunicator(application, "/ws/chat/")
    connected, _ = await communicator.connect()
    assert connected
    await communicator.disconnect()
