import json

import pytest
from channels.testing import WebsocketCommunicator

from config import asgi


@pytest.mark.asyncio
async def test_chat_consumer_connection() -> None:
    communicator = WebsocketCommunicator(asgi.application, "/ws/chat/")
    connected, _ = await communicator.connect()
    assert connected
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_chat_consumer_streaming() -> None:
    communicator = WebsocketCommunicator(asgi.application, "/ws/chat/")
    await communicator.connect()

    # Mock the LLM service
    from typing import Any, AsyncGenerator
    from unittest.mock import patch

    with patch("chat.consumers.LLMService.stream_chat") as mock_stream:

        async def mock_gen(messages: Any) -> AsyncGenerator[str, None]:
            yield "Hello"
            yield " world"

        mock_stream.return_value = mock_gen(None)

        # Use send_input for text data
        await communicator.send_input({"type": "websocket.receive", "text": json.dumps({"message": "Hi"})})

        # 1. User message response
        resp = await communicator.receive_from()
        assert 'id="messages"' in resp
        assert "bg-blue-600" in resp

        # 2. Assistant block start
        resp = await communicator.receive_from()
        assert 'id="messages"' in resp
        assert "bg-gray-800" in resp

        # 3. First chunk
        resp = await communicator.receive_from()
        assert "Hello" in resp
        assert "hx-swap-oob" in resp

        # 4. Second chunk
        resp = await communicator.receive_from()
        assert " world" in resp
        assert "hx-swap-oob" in resp

    await communicator.disconnect()
