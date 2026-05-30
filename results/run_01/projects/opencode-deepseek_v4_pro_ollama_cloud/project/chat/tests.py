from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

from channels.testing import WebsocketCommunicator
from django.test import TestCase
from django.test.client import RequestFactory

from chat.services import stream_response
from chat.views import chat_page, health_check
from config.asgi import application


class FakeStreamChunk:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeChatOllama:
    def __init__(self, model: str = "test", base_url: str = "http://test") -> None:
        self.model = model
        self.base_url = base_url
        self._invoke_calls: list[list[dict[str, str]]] = []

    async def ainvoke(self, messages: list[dict[str, str]]) -> FakeStreamChunk:
        self._invoke_calls.append(messages)
        return FakeStreamChunk("ok")

    async def astream(self, messages: list[dict[str, str]]) -> Any:
        self._invoke_calls.append(messages)
        for token_text in ["Hello", " ", "World", "!"]:
            yield FakeStreamChunk(token_text)


class HealthCheckViewTests(TestCase):
    async def test_health_check_returns_json(self) -> None:
        factory = RequestFactory()
        request = factory.get("/health/")
        with patch(
            "chat.views.check_ollama_reachability",
            new=AsyncMock(return_value=True),
        ):
            response = await health_check(request)
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["ollama_reachable"] is True
        assert "ollama_host" in data
        assert "ollama_model" in data

    async def test_health_check_unreachable(self) -> None:
        factory = RequestFactory()
        request = factory.get("/health/")
        with patch(
            "chat.views.check_ollama_reachability",
            new=AsyncMock(return_value=False),
        ):
            response = await health_check(request)
        data = json.loads(response.content)
        assert data["ollama_reachable"] is False


class ChatPageViewTests(TestCase):
    def test_chat_page_renders(self) -> None:
        factory = RequestFactory()
        request = factory.get("/")
        response = chat_page(request)
        assert response.status_code == 200
        content = response.content.decode()
        assert "ws-connect" in content
        assert "/ws/chat/" in content
        assert "Welcome to Chat" in content
        assert "htmx-ext-ws" in content
        assert "ws-send" in content


class ServicesTests(TestCase):
    async def test_stream_response_yields_tokens(self) -> None:
        fake_client = FakeChatOllama()
        messages = [{"role": "user", "content": "hi"}]

        with patch("chat.services.build_chat_ollama", return_value=fake_client):
            tokens = [t async for t in stream_response(messages)]

        assert tokens == ["Hello", " ", "World", "!"]

    async def test_stream_response_single_token(self) -> None:
        class SingleTokenFake:
            async def astream(self, messages):  # type: ignore[no-untyped-def]
                yield FakeStreamChunk("solotoken")

        with patch(
            "chat.services.build_chat_ollama",
            return_value=SingleTokenFake(),
        ):
            tokens = [t async for t in stream_response([])]
        assert tokens == ["solotoken"]


class ConsumerTests(TestCase):
    async def test_connect_and_disconnect(self) -> None:
        communicator = WebsocketCommunicator(application=application, path="/ws/chat/")
        connected, _ = await communicator.connect()
        assert connected

        resp = await communicator.receive_json_from()
        assert resp["type"] == "system"
        assert "Connected" in resp["content"]

        await communicator.disconnect()

    async def test_send_message_and_stream(self) -> None:
        async def fake_stream(messages):  # type: ignore[no-untyped-def]
            for token_text in ["Hello", " ", "World", "!"]:
                yield token_text

        with patch("chat.consumers.stream_response", new=fake_stream):
            communicator = WebsocketCommunicator(application=application, path="/ws/chat/")
            connected, _ = await communicator.connect()
            assert connected
            _ = await communicator.receive_json_from()

            await communicator.send_json_to({"message": "Hello"})

            msg_user = await communicator.receive_json_from()
            assert msg_user["type"] == "user"
            assert msg_user["content"] == "Hello"

            tokens_collected: list[str] = []
            while True:
                msg = await communicator.receive_json_from()
                if msg["type"] == "assistant_token":
                    tokens_collected.append(msg["content"])
                elif msg["type"] == "assistant_done":
                    break

            assert "".join(tokens_collected) == "Hello World!"

            await communicator.disconnect()

    async def test_empty_message_error(self) -> None:
        communicator = WebsocketCommunicator(application=application, path="/ws/chat/")
        connected, _ = await communicator.connect()
        assert connected
        _ = await communicator.receive_json_from()

        await communicator.send_json_to({"message": "  "})

        msg = await communicator.receive_json_from()
        assert msg["type"] == "error"
        assert "Empty" in msg["content"]

        await communicator.disconnect()
