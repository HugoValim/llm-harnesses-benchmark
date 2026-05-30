from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from channels.testing import WebsocketCommunicator

from config.asgi import application


@pytest.fixture
async def communicator():
    comm = WebsocketCommunicator(application, "/ws/chat/")
    connected, _ = await comm.connect()
    assert connected
    yield comm
    await comm.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_websocket_connects():
    comm = WebsocketCommunicator(application, "/ws/chat/")
    connected, _ = await comm.connect()
    assert connected
    await comm.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_websocket_receives_error_on_invalid_json(communicator):
    await communicator.send_to(text_data="not json")
    response = await communicator.receive_output(timeout=5)
    text = response["text"]
    assert "Invalid message format" in text or "Invalid" in text


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_websocket_ignores_empty_message(communicator):
    await communicator.send_to(text_data=json.dumps({"message": ""}))
    assert await communicator.receive_nothing(timeout=0.5)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_websocket_streams_tokens_from_ollama(communicator):
    fake_chunks = ["Hello", " world", "!"]

    async def mock_astream(self, messages, **kwargs):
        for chunk_text in fake_chunks:
            msg = AsyncMock()
            msg.content = chunk_text
            yield msg

    with patch("chat.llm.ChatOllama.astream", mock_astream):
        await communicator.send_to(text_data=json.dumps({"message": "Hi"}))

        # First token creates the message div
        first_response = await communicator.receive_output(timeout=5)
        first_html = first_response["text"]
        assert "msg-0" in first_html
        assert "Hello" in first_html

        # Subsequent tokens update via OOB swap
        for _ in range(1, len(fake_chunks)):
            response = await communicator.receive_output(timeout=5)
            html = response["text"]
            assert "hx-swap-oob" in html
            assert "msg-0-content" in html


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_websocket_reports_ollama_unreachable(communicator):
    import httpx

    with patch(
        "chat.llm.ChatOllama.astream",
        side_effect=httpx.ConnectError("Connection refused"),
    ):
        await communicator.send_to(text_data=json.dumps({"message": "Hi"}))

        response = await communicator.receive_output(timeout=5)
        html = response["text"]
        assert "Ollama" in html


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_websocket_multi_turn_conversation(communicator):
    """Verify conversation history is maintained across messages."""
    call_count = 0
    received_messages = []

    async def mock_astream(self, messages, **kwargs):
        nonlocal call_count
        call_count += 1
        received_messages.append(list(messages))
        msg = AsyncMock()
        msg.content = f"Response {call_count}"
        yield msg

    with patch("chat.llm.ChatOllama.astream", mock_astream):
        # First message
        await communicator.send_to(text_data=json.dumps({"message": "Hello"}))
        await communicator.receive_output(timeout=5)

        # Second message — conversation should have history
        await communicator.send_to(text_data=json.dumps({"message": "How are you?"}))
        await communicator.receive_output(timeout=5)

    # Second call should have received the full conversation history
    assert len(received_messages) == 2
    assert len(received_messages[1]) >= 3  # user + assistant from first + user second


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_websocket_html_escaping(communicator):
    """Verify that HTML special characters in streamed content are escaped."""

    async def mock_astream(self, messages, **kwargs):
        msg = AsyncMock()
        msg.content = "<script>alert('xss')</script>"
        yield msg

    with patch("chat.llm.ChatOllama.astream", mock_astream):
        await communicator.send_to(text_data=json.dumps({"message": "test"}))

        response = await communicator.receive_output(timeout=5)
        html = response["text"]
        assert "&lt;script&gt;" in html
