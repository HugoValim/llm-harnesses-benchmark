from collections.abc import AsyncIterator, Sequence

import pytest

from chat.llm import OllamaChatStreamer
from chat.messages import ChatTurn


class FakeChunk:
    def __init__(self, content: object) -> None:
        self.content = content


class FakeChatOllama:
    instances: list["FakeChatOllama"] = []

    def __init__(self, *, model: str, base_url: str) -> None:
        self.model = model
        self.base_url = base_url
        self.messages: list[object] = []
        FakeChatOllama.instances.append(self)

    async def astream(self, messages: Sequence[object]) -> AsyncIterator[object]:
        self.messages = list(messages)
        yield FakeChunk("Hel")
        yield FakeChunk([{"text": "lo"}])


@pytest.mark.asyncio
async def test_ollama_streamer_uses_chatollama_and_streams_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeChatOllama.instances.clear()
    monkeypatch.setenv("OLLAMA_HOST", "http://ollama.test:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen-custom")
    monkeypatch.setattr("chat.llm.ChatOllama", FakeChatOllama)

    streamer = OllamaChatStreamer()
    chunks = [
        chunk
        async for chunk in streamer.stream_reply(
            [ChatTurn(role="user", content="Hello")]
        )
    ]

    assert chunks == ["Hel", "lo"]
    assert FakeChatOllama.instances[0].base_url == "http://ollama.test:11434"
    assert FakeChatOllama.instances[0].model == "qwen-custom"
    assert len(FakeChatOllama.instances[0].messages) == 1
