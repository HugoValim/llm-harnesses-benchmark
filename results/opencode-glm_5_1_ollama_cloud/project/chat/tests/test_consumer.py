import json
from unittest.mock import patch

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


class TestChatConsumerConnect:
    @pytest.mark.asyncio
    async def test_connect_success(self):
        communicator = WebsocketCommunicator(application, "/ws/chat/")
        connected, _ = await communicator.connect()
        assert connected
        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_disconnect_cleans_state(self):
        communicator = WebsocketCommunicator(application, "/ws/chat/")
        await communicator.connect()
        await communicator.disconnect()


class TestChatConsumerMessaging:
    @pytest.mark.asyncio
    async def test_send_message_receives_tokens(self, communicator):
        fake_chunks = ["Hi", " there", "!"]
        with patch("chat.consumers.stream_response") as mock_stream:

            async def fake_stream(messages):
                for chunk in fake_chunks:
                    yield chunk

            mock_stream.side_effect = fake_stream

            await communicator.send_to(text_data=json.dumps({"message": "hello"}))

            received_texts = []
            for _ in range(len(fake_chunks) + 1):
                resp = await communicator.receive_from(timeout=5)
                data = json.loads(resp)
                received_texts.append(data)

            token_msgs = [m for m in received_texts if m["type"] == "token"]
            assert len(token_msgs) == 3
            assert token_msgs[0]["content"] == "Hi"
            assert token_msgs[1]["content"] == " there"
            assert token_msgs[2]["content"] == "!"

            done_msgs = [m for m in received_texts if m["type"] == "done"]
            assert len(done_msgs) == 1
            assert done_msgs[0]["content"] == "Hi there!"

    @pytest.mark.asyncio
    async def test_empty_message_ignored(self, communicator):
        with patch("chat.consumers.stream_response") as mock_stream:
            await communicator.send_to(text_data=json.dumps({"message": ""}))
            await communicator.send_to(text_data=json.dumps({"message": "   "}))
            mock_stream.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_json_returns_error(self, communicator):
        await communicator.send_to(text_data="not json")
        resp = await communicator.receive_from(timeout=5)
        data = json.loads(resp)
        assert data["type"] == "error"
        assert "Invalid JSON" in data["content"]

    @pytest.mark.asyncio
    async def test_stream_error_returns_error_message(self, communicator):
        with patch("chat.consumers.stream_response") as mock_stream:

            async def failing_stream(messages):
                raise ConnectionError("Ollama down")
                yield  # noqa: E501 - unreachable yield makes this an async generator

            mock_stream.side_effect = failing_stream

            await communicator.send_to(text_data=json.dumps({"message": "test"}))

            resp = await communicator.receive_from(timeout=5)
            data = json.loads(resp)
            assert data["type"] == "error"
            assert "Ollama down" in data["content"]

    @pytest.mark.asyncio
    async def test_multi_turn_conversation(self, communicator):
        call_count = 0

        with patch("chat.consumers.stream_response") as mock_stream:

            async def fake_stream(messages):
                nonlocal call_count
                call_count += 1
                yield f"Response {call_count}"

            mock_stream.side_effect = fake_stream

            await communicator.send_to(text_data=json.dumps({"message": "first"}))

            messages = []
            while True:
                resp = await communicator.receive_from(timeout=5)
                data = json.loads(resp)
                messages.append(data)
                if data["type"] == "done":
                    break

            await communicator.send_to(text_data=json.dumps({"message": "second"}))
            while True:
                resp = await communicator.receive_from(timeout=5)
                data = json.loads(resp)
                messages.append(data)
                if data["type"] == "done":
                    break

            done_msgs = [m for m in messages if m["type"] == "done"]
            assert len(done_msgs) == 2
