"""WebSocket consumer tests using Channels' ``WebsocketCommunicator``.

The LLM boundary is replaced with :class:`tests.fakes.FakeChatService` so no
real Ollama/LangChain call happens. Tests assert that multiple streamed chunks
reach the socket (not just the final concatenated message), that the error path
renders an error partial, and that multi-turn context accumulates.
"""

from __future__ import annotations

import json

import pytest
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator

from chat import consumers
from chat.routing import websocket_urlpatterns
from chat.services import OllamaUnavailableError
from tests.fakes import FakeChatService


def _build_app() -> URLRouter:
    """Fresh websocket application instance for one communicator."""
    return URLRouter(websocket_urlpatterns)


async def _drain_until_stream_end(communicator: WebsocketCommunicator) -> list[str]:
    """Collect frames until the stream-end partial (caret removal) arrives."""
    frames: list[str] = []
    while True:
        frame = await communicator.receive_from(timeout=2)
        frames.append(frame)
        if "assistant-typing-" in frame and 'hx-swap-oob="true"' in frame:
            return frames


async def test_consumer_streams_multiple_token_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeChatService(tokens=["Hel", "lo", " wor", "ld"])
    monkeypatch.setattr(consumers, "create_chat_service", lambda: fake)

    communicator = WebsocketCommunicator(_build_app(), "/ws/chat/")
    connected, _ = await communicator.connect()
    assert connected

    await communicator.send_to(text_data=json.dumps({"message": "say hi"}))
    frames = await _drain_until_stream_end(communicator)

    # The user echo and the assistant shell precede the token frames.
    assert any("say hi" in f for f in frames)
    assert any('id="assistant-content-1"' in f for f in frames)

    token_frames = [f for f in frames if "beforeend:#assistant-content-1" in f]
    assert len(token_frames) == 4  # one frame per streamed chunk, not a single blob
    streamed = "".join(f.split(">", 1)[1].rsplit("<", 1)[0] for f in token_frames)
    assert streamed == "Hello world"

    await communicator.disconnect()


async def test_consumer_renders_error_partial_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeChatService(error=OllamaUnavailableError("ollama down"))
    monkeypatch.setattr(consumers, "create_chat_service", lambda: fake)

    communicator = WebsocketCommunicator(_build_app(), "/ws/chat/")
    connected, _ = await communicator.connect()
    assert connected

    await communicator.send_to(text_data=json.dumps({"message": "hello"}))
    frames = await _drain_until_stream_end(communicator)

    assert any("The assistant is unavailable" in f for f in frames)
    assert any("ollama down" in f for f in frames)

    await communicator.disconnect()


async def test_consumer_keeps_multi_turn_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeChatService(tokens=["ok"])
    monkeypatch.setattr(consumers, "create_chat_service", lambda: fake)

    communicator = WebsocketCommunicator(_build_app(), "/ws/chat/")
    connected, _ = await communicator.connect()
    assert connected

    await communicator.send_to(text_data=json.dumps({"message": "first"}))
    await _drain_until_stream_end(communicator)
    await communicator.send_to(text_data=json.dumps({"message": "second"}))
    await _drain_until_stream_end(communicator)

    # On the second turn the history carries the first exchange plus the new prompt.
    roles = [turn.role for turn in fake.received_history]
    contents = [turn.content for turn in fake.received_history]
    assert roles == ["human", "ai", "human"]
    assert contents == ["first", "ok", "second"]

    await communicator.disconnect()


async def test_consumer_ignores_blank_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeChatService(tokens=["unused"])
    monkeypatch.setattr(consumers, "create_chat_service", lambda: fake)

    communicator = WebsocketCommunicator(_build_app(), "/ws/chat/")
    connected, _ = await communicator.connect()
    assert connected

    await communicator.send_to(text_data=json.dumps({"message": "   "}))
    assert await communicator.receive_nothing(timeout=0.5) is True

    await communicator.disconnect()


async def test_disconnect_cancels_in_flight_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A slow stream guarantees the reply task is still running at disconnect,
    # exercising the cancellation/cleanup path rather than a no-op disconnect.
    fake = FakeChatService(tokens=["a", "b", "c", "d", "e"], per_token_delay=0.05)
    monkeypatch.setattr(consumers, "create_chat_service", lambda: fake)

    communicator = WebsocketCommunicator(_build_app(), "/ws/chat/")
    connected, _ = await communicator.connect()
    assert connected

    await communicator.send_to(text_data=json.dumps({"message": "stream please"}))
    # Receive the user echo + assistant shell, then disconnect mid-stream.
    await communicator.receive_from(timeout=2)
    await communicator.receive_from(timeout=2)
    await communicator.disconnect()  # must not raise; cancels the live task


def test_asgi_application_routes_http_and_websocket() -> None:
    from config.asgi import application

    assert callable(application)
    assert set(application.application_mapping) == {"http", "websocket"}
