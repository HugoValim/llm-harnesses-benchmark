import asyncio
from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
from channels.testing import WebsocketCommunicator

from config.asgi import application


class FakeChunk:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeChatOllama:
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    async def astream(self, messages: list[dict[str, str]]) -> AsyncIterator[FakeChunk]:
        for text in self._chunks:
            yield FakeChunk(content=text)


class FakeLLMService:
    """Named fake LLM service for consumer tests."""

    def __init__(self) -> None:
        self.host = "http://localhost:11434"
        self.model = "qwen2.5:7b"

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        for token in ["Hello", " ", "world"]:
            yield token


@pytest.mark.asyncio
async def test_consumer_streams_tokens() -> None:
    fake_llm = FakeLLMService()

    with patch("chat.consumers.LLMService", return_value=fake_llm):
        comm = WebsocketCommunicator(application, "/ws/chat/")
        connected, _ = await comm.connect()
        assert connected

        await comm.send_json_to({"message": "hi"})

        messages = []
        while True:
            try:
                resp = await comm.receive_json_from(timeout=2)
                messages.append(resp)
                if resp.get("type") == "stream_end":
                    break
            except Exception:
                break

        await asyncio.sleep(0.1)
        try:
            await comm.disconnect()
        except asyncio.CancelledError:
            pass

    types = [m["type"] for m in messages]
    assert "stream_start" in types
    assert "stream_end" in types
    tokens = [m for m in messages if m["type"] == "token"]
    assert len(tokens) == 3
    combined = "".join(t["content"] for t in tokens)
    assert combined == "Hello world"


@pytest.mark.asyncio
async def test_consumer_rejects_empty_message() -> None:
    comm = WebsocketCommunicator(application, "/ws/chat/")
    connected, _ = await comm.connect()
    assert connected

    await comm.send_json_to({"message": "   "})
    resp = await comm.receive_json_from(timeout=2)
    assert "error" in resp

    await comm.disconnect()


@pytest.mark.asyncio
async def test_consumer_rejects_invalid_json() -> None:
    comm = WebsocketCommunicator(application, "/ws/chat/")
    connected, _ = await comm.connect()
    assert connected

    await comm.send_to(text_data="not json")
    resp = await comm.receive_json_from(timeout=2)
    assert "error" in resp

    await comm.disconnect()


class FailingLLMService:
    """Named fake that simulates LLM streaming failure."""

    def __init__(self) -> None:
        self.host = "http://localhost:11434"
        self.model = "qwen2.5:7b"

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        raise ConnectionError("Ollama not reachable")
        yield  # unreachable


@pytest.mark.asyncio
async def test_consumer_handles_streaming_error() -> None:
    fake_llm = FailingLLMService()

    with patch("chat.consumers.LLMService", return_value=fake_llm):
        comm = WebsocketCommunicator(application, "/ws/chat/")
        connected, _ = await comm.connect()
        assert connected

        await comm.send_json_to({"message": "hi"})

        messages = []
        while True:
            try:
                resp = await comm.receive_json_from(timeout=2)
                messages.append(resp)
                if resp.get("type") == "error":
                    break
            except Exception:
                break

        await asyncio.sleep(0.1)
        try:
            await comm.disconnect()
        except asyncio.CancelledError:
            pass

    errors = [m for m in messages if m["type"] == "error"]
    assert len(errors) == 1
    assert "Ollama not reachable" in errors[0]["content"]


@pytest.mark.asyncio
async def test_consumer_ignores_binary_data() -> None:
    comm = WebsocketCommunicator(application, "/ws/chat/")
    connected, _ = await comm.connect()
    assert connected

    await comm.send_to(bytes_data=b"binary stuff")
    # Consumer returns early for binary data — no response expected.
    # Give it a moment to process.
    await asyncio.sleep(0.1)

    await comm.disconnect()
