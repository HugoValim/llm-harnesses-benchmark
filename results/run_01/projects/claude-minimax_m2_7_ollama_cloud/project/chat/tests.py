"""Tests for chat app."""

import json
import os
from unittest.mock import patch

import pytest
from channels.testing import WebsocketCommunicator
from django.test import Client

from chat.consumers import ChatConsumer
from chat.llm_service import OllamaService


class TestOllamaService:
    """Tests for the Ollama LLM service."""

    def test_service_reads_env_vars(self):
        with patch.dict(
            os.environ,
            {"OLLAMA_HOST": "http://custom:9999", "OLLAMA_MODEL": "custom-model"},
            clear=False,
        ):
            service = OllamaService()
            assert service.host == "http://custom:9999"
            assert service.model == "custom-model"

    def test_service_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            service = OllamaService()
            assert service.host == "http://localhost:11434"
            assert service.model == "qwen2.5:7b"

    @pytest.mark.asyncio
    async def test_stream_chat_yields_chunks(self, fake_chat_chunk):
        """Assert multiple chunks are yielded from the async iterator."""
        service = OllamaService()

        class FakeClient:
            async def astream(self, messages):
                for chunk in fake_chat_chunk:
                    yield chunk

        service._client = FakeClient()  # noqa: SLF001

        chunks = [chunk async for chunk in service.stream_chat([])]

        assert len(chunks) == 3
        assert chunks[0] == "Hello, "
        assert chunks[1] == "world!"
        assert chunks[2] == " How can I help?"


class TestChatConsumer:
    """Tests for the WebSocket chat consumer."""

    @pytest.mark.asyncio
    async def test_connect_accepts_websocket(self):
        """WebSocket connection is accepted."""
        communicator = WebsocketCommunicator(
            ChatConsumer.as_asgi(), "/ws/chat/"
        )
        connected, _ = await communicator.connect()
        assert connected is True
        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_receive_invalid_json_returns_error(self):
        """Invalid JSON produces an error message."""
        communicator = WebsocketCommunicator(
            ChatConsumer.as_asgi(), "/ws/chat/"
        )
        await communicator.connect()

        await communicator.send_to(text_data="not valid json")
        response = await communicator.receive_from()

        data = json.loads(response)
        assert data["type"] == "error"
        assert "Invalid JSON" in data["content"]
        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_receive_empty_message_returns_error(self):
        """Empty message string produces an error."""
        communicator = WebsocketCommunicator(
            ChatConsumer.as_asgi(), "/ws/chat/"
        )
        await communicator.connect()

        await communicator.send_json_to({"message": "   "})
        response = await communicator.receive_from()

        data = json.loads(response)
        assert data["type"] == "error"
        assert "Empty message" in data["content"]
        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_receive_streams_chunks_via_fake_llm(self):
        """Multiple .stream() chunks are forwarded over WebSocket."""
        communicator = WebsocketCommunicator(
            ChatConsumer.as_asgi(), "/ws/chat/"
        )
        await communicator.connect()

        async def fake_astream(messages):
            for chunk_text in ["Hello, ", "world!"]:
                yield chunk_text

        with patch("chat.consumers.ollama_service") as mock_service:
            mock_service.stream_chat = fake_astream

            await communicator.send_json_to({"message": "Hi there"})

            responses = []
            while True:
                msg = await communicator.receive_from()
                data = json.loads(msg)
                responses.append(data)
                if data["type"] == "done":
                    break

            assert len(responses) == 3
            assert responses[0]["type"] == "text"
            assert responses[0]["content"] == "Hello, "
            assert responses[1]["type"] == "text"
            assert responses[1]["content"] == "world!"
            assert responses[2]["type"] == "done"

        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_receive_error_from_llm_propagates(self):
        """LLM exceptions are sent as error messages."""
        communicator = WebsocketCommunicator(
            ChatConsumer.as_asgi(), "/ws/chat/"
        )
        await communicator.connect()

        class FakeFailingIterator:
            def __aiter__(self):
                return self

            async def __anext__(self):
                msg = "Ollama unreachable"
                raise RuntimeError(msg)

        def fake_fail(messages):
            return FakeFailingIterator()

        with patch("chat.consumers.ollama_service") as mock_service:
            mock_service.stream_chat = fake_fail

            await communicator.send_json_to({"message": "Hello"})
            response = await communicator.receive_from()

            data = json.loads(response)
            assert data["type"] == "error"
            assert "Ollama unreachable" in data["content"]

        await communicator.disconnect()


class TestViews:
    """Tests for Django views."""

    def test_chat_view_returns_template(self):
        """GET / renders the chat SPA template."""
        client = Client()
        response = client.get("/")
        assert response.status_code == 200
        assert "chat/index.html" in [t.name for t in response.templates]

    def test_health_view_returns_json(self):
        """GET /health/ returns JSON with Ollama status."""
        client = Client()
        with patch("chat.views.ollama_service") as mock_svc:
            mock_svc.health_check.return_value = {
                "status": "ok",
                "host": "http://localhost:11434",
                "model": "qwen2.5:7b",
            }
            response = client.get("/health/")
            assert response.status_code == 200
            data = json.loads(response.content)
            assert data["status"] == "ok"


class TestTemplateRendering:
    """Tests that templates and partials render correctly."""

    def test_index_template_renders_without_error(self):
        """The main index.html template renders without exceptions."""
        client = Client()
        response = client.get("/")
        assert response.status_code == 200
        assert b"chat-container" in response.content

    def test_static_files_included(self):
        """HTMX and WebSocket JS are referenced in the template."""
        client = Client()
        response = client.get("/")
        content = response.content.decode()
        assert "htmx.min.js" in content
        assert "ws.js" in content
