import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from channels.testing import WebsocketCommunicator

from chat.consumers import ChatConsumer


class FakeAsyncIterator:
    def __init__(self, items: list[str]) -> None:
        self.items = items
        self.index = 0

    def __aiter__(self) -> "FakeAsyncIterator":
        return self

    async def __anext__(self) -> str:
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item


@pytest.fixture
def mock_channel_layer() -> MagicMock:
    layer = MagicMock()
    layer.group_add = AsyncMock()
    layer.group_discard = AsyncMock()
    layer.group_send = AsyncMock()
    return layer


@pytest.mark.asyncio
async def test_consumer_connect(mock_channel_layer: MagicMock) -> None:
    communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), "/ws/chat/test-session/")
    communicator.scope["channel_layer"] = mock_channel_layer  # type: ignore[typeddict-unknown-key]

    connected, _ = await communicator.connect()
    assert connected

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_consumer_disconnect_runs_without_error(mock_channel_layer: MagicMock) -> None:
    communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), "/ws/chat/test-session/")
    communicator.scope["channel_layer"] = mock_channel_layer  # type: ignore[typeddict-unknown-key]

    connected, _ = await communicator.connect()
    assert connected

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_consumer_receive_invalid_json(mock_channel_layer: MagicMock) -> None:
    communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), "/ws/chat/test-session/")
    communicator.scope["channel_layer"] = mock_channel_layer  # type: ignore[typeddict-unknown-key]

    connected, _ = await communicator.connect()
    assert connected

    await communicator.send_to(text_data="not valid json{{{")
    response = await communicator.receive_json_from()

    assert response.get("error") == "Invalid JSON"

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_consumer_receive_empty_message(mock_channel_layer: MagicMock) -> None:
    communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), "/ws/chat/test-session/")
    communicator.scope["channel_layer"] = mock_channel_layer  # type: ignore[typeddict-unknown-key]

    connected, _ = await communicator.connect()
    assert connected

    await communicator.send_json_to({"message": ""})
    response = await communicator.receive_json_from()

    assert response.get("error") == "No message provided"

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_consumer_stream_yields_chunks(mock_channel_layer: MagicMock) -> None:
    fake_stream = FakeAsyncIterator(["chunk1", "chunk2", "chunk3"])

    with patch("chat.consumers.get_ollama_service") as mock_get_service:
        mock_service = MagicMock()
        mock_service.astream = MagicMock(return_value=fake_stream)
        mock_get_service.return_value = mock_service

        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), "/ws/chat/test-session/")
        communicator.scope["channel_layer"] = mock_channel_layer  # type: ignore[typeddict-unknown-key]

        connected, _ = await communicator.connect()
        assert connected

        await communicator.send_json_to({"message": "Hello"})

        tokens: list[str] = []
        timeout = 5
        start = asyncio.get_event_loop().time()
        while len(tokens) < 3:
            if asyncio.get_event_loop().time() - start > timeout:
                break
            try:
                response = await communicator.receive_json_from(timeout=2)
                if "token" in response:
                    tokens.append(response["token"])
                if response.get("done"):
                    break
            except TimeoutError:
                break

        assert len(tokens) == 3
        assert tokens[0] == "chunk1"
        assert tokens[1] == "chunk2"
        assert tokens[2] == "chunk3"

        await communicator.disconnect()
