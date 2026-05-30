import json
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from channels.testing import WebsocketCommunicator

from chat.consumers import ChatConsumer


class _FakeLLM:
    """Stand-in for ChatOllama that returns canned chunks."""

    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    class _FakeAIMessageChunk:
        def __init__(self, content: str) -> None:
            self.content = content

    async def astream(self, messages: list[dict[str, str]]) -> AsyncGenerator[object]:
        for c in self._chunks:
            yield self._FakeAIMessageChunk(content=c)


async def _stream_then_fail(
    messages: list[dict[str, str]],
) -> AsyncGenerator[str]:
    """Yield a partial response, then raise."""
    yield "par"
    raise ConnectionError("fake failure")


@pytest.mark.asyncio
async def test_consumer_connect(monkeypatch: Any) -> None:
    """Verify WebSocket connects."""
    import chat.llm_service

    monkeypatch.setattr(
        chat.llm_service,
        "_build_llm",
        lambda: _FakeLLM(chunks=["hello"]),
    )

    communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), "/ws/chat/")
    connected, _ = await communicator.connect()
    assert connected
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_consumer_returns_error_on_failure(monkeypatch: Any) -> None:
    """Verify error when stream_response raises."""
    import chat.consumers as cons_module

    monkeypatch.setattr(cons_module, "stream_response", _stream_then_fail)

    communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), "/ws/chat/")
    connected, _ = await communicator.connect()
    assert connected

    await communicator.send_to(text_data=json.dumps({"message": "hello"}))

    # First gets the partial chunk
    resp1 = await communicator.receive_from()
    assert json.loads(resp1)["type"] == "chunk"

    # Then gets the error
    resp2 = await communicator.receive_from()
    assert json.loads(resp2)["type"] == "error"

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_consumer_streams_chunks(monkeypatch: Any) -> None:
    """Verify multiple streamed chunks arrive before done signal."""
    import chat.llm_service

    monkeypatch.setattr(
        chat.llm_service,
        "_build_llm",
        lambda: _FakeLLM(chunks=["Hel", "lo ", "world"]),
    )

    communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), "/ws/chat/")
    connected, _ = await communicator.connect()
    assert connected

    await communicator.send_to(text_data=json.dumps({"message": "hi"}))
    received: list[str] = []
    for _ in range(3):
        msg = await communicator.receive_from()
        received.append(msg)
    done = await communicator.receive_from()

    contents = "".join(json.loads(m)["content"] for m in received)
    assert contents == "Hello world"
    assert json.loads(done)["type"] == "done"

    await communicator.disconnect()
