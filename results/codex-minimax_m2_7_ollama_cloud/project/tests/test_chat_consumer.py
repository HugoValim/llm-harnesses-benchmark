"""Tests for the WebSocket consumer."""

from unittest.mock import MagicMock, patch

import pytest
from channels.auth import AuthMiddlewareStack
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator

from chat.routing import websocket_urlpatterns
from chat.services.llm import ChatService, OllamaConnectionError


@pytest.fixture
def fake_chunks():
    return ["Hello", " ", "world", "!"]


def _make_app():
    return AuthMiddlewareStack(URLRouter(websocket_urlpatterns))


@pytest.mark.asyncio
class TestChatConsumer:
    """Tests for ChatConsumer with WebsocketCommunicator."""

    async def _make_communicator(self):
        return WebsocketCommunicator(_make_app(), "/ws/chat/")

    async def test_connect_accepted(self):
        """WebSocket connection is accepted."""
        communicator = await self._make_communicator()
        connected, _ = await communicator.connect()
        assert connected is True
        await communicator.disconnect()

    async def test_disconnect_cleans_up(self):
        """Disconnection completes without error."""
        communicator = await self._make_communicator()
        await communicator.connect()
        await communicator.disconnect()

    async def test_reset_action_clears_history(self, fake_chunks):
        """Reset action returns done message."""

        async def fake_stream(prompt: str):
            for chunk in fake_chunks:
                yield chunk

        with patch.object(ChatService, "astream_tokens", side_effect=fake_stream):
            communicator = await self._make_communicator()
            await communicator.connect()
            await communicator.send_json_to({"action": "reset", "prompt": ""})
            response = await communicator.receive_json_from(timeout=5)
            assert response.get("type") == "reset"
            assert response.get("done") is True
            await communicator.disconnect()

    async def test_chat_action_streams_multiple_tokens(self, fake_chunks):
        """Chat action streams multiple token chunks to the client."""

        async def fake_stream(prompt: str):
            for chunk in fake_chunks:
                yield chunk

        with patch.object(ChatService, "astream_tokens", side_effect=fake_stream):
            communicator = await self._make_communicator()
            await communicator.connect()
            await communicator.send_json_to({"action": "chat", "prompt": "Hi"})

            tokens = []
            done_seen = False
            final_content = ""

            while True:
                msg = await communicator.receive_json_from(timeout=5)
                msg_type = msg.get("type")
                if msg_type == "start":
                    pass
                elif msg_type == "token":
                    tokens.append(msg.get("content", ""))
                elif msg_type == "done":
                    done_seen = True
                    final_content = msg.get("content", "")
                    break
                elif msg_type == "error":
                    pytest.fail(f"Unexpected error: {msg.get('error')}")

            assert tokens == fake_chunks
            assert done_seen is True
            assert final_content == "".join(fake_chunks)
            await communicator.disconnect()

    async def test_empty_prompt_returns_error(self):
        """Empty prompt is rejected with an error."""
        communicator = await self._make_communicator()
        await communicator.connect()
        await communicator.send_json_to({"action": "chat", "prompt": ""})

        response = await communicator.receive_json_from(timeout=5)
        assert response.get("type") == "error"
        assert "prompt" in response.get("error", "").lower()
        await communicator.disconnect()

    async def test_unknown_action_returns_error(self):
        """Unknown action is rejected."""
        communicator = await self._make_communicator()
        await communicator.connect()
        await communicator.send_json_to({"action": "bogus"})

        response = await communicator.receive_json_from(timeout=5)
        assert response.get("type") == "error"
        assert "Unknown action" in response.get("error", "")
        await communicator.disconnect()

    async def test_ollama_unreachable_returns_error(self):
        """Ollama connection failure surfaces as typed error message."""

        async def failing_stream(prompt: str):
            # yield one chunk so async for can start, then raise
            yield "x"
            raise OllamaConnectionError("http://localhost:11434", "refused")

        with patch.object(ChatService, "astream_tokens", side_effect=failing_stream):
            communicator = await self._make_communicator()
            await communicator.connect()
            await communicator.send_json_to({"action": "chat", "prompt": "Hi"})

            seen_types = set()
            while len(seen_types) < 5:
                msg = await communicator.receive_json_from(timeout=5)
                seen_types.add(msg.get("type"))
                if msg.get("type") == "error":
                    assert "Ollama" in msg.get("error", "")
                    break
            else:
                pytest.fail(f"Never received error response; got: {seen_types}")

            await communicator.disconnect()


@pytest.mark.asyncio
class TestChatService:
    """Unit tests for ChatService (mocked LangChain path)."""

    class FakeChunk:
        def __init__(self, content: str) -> None:
            self.content = content

    async def test_service_yields_chunks(self, fake_chunks):
        """Service async iterator yields all chunks."""
        service = ChatService()
        mock_client = MagicMock()

        async def fake_astream(messages):
            for chunk in fake_chunks:
                yield self.FakeChunk(chunk)

        mock_client.astream = fake_astream
        service._client = mock_client

        tokens = [token async for token in service.astream_tokens_simple("Hi")]
        assert tokens == fake_chunks

    async def test_service_handles_ollama_error(self):
        """Service wraps Ollama errors in OllamaConnectionError."""
        service = ChatService()
        mock_client = MagicMock()

        async def bad_stream(messages):
            yield self.FakeChunk("partial")
            raise ConnectionError("refused")

        mock_client.astream = bad_stream
        service._client = mock_client

        with pytest.raises(OllamaConnectionError):
            async for _ in service.astream_tokens_simple("Hi"):
                pass

    async def test_reset_history_clears_messages(self):
        """reset_history removes conversation history."""
        service = ChatService()
        mock_client = MagicMock()

        async def fake_astream(messages):
            yield self.FakeChunk("ok")

        mock_client.astream = fake_astream
        service._client = mock_client

        async for _ in service.astream_tokens("Hello"):
            pass

        assert len(service._history) > 0
        service.reset_history()
        assert len(service._history) == 0
