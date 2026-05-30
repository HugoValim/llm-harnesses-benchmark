import pytest

from chat.services import OllamaChatService


class FakeChatOllama:
    def __init__(self, model, base_url):
        self.model = model
        self.base_url = base_url
        self._messages = None

    def astream(self, messages):
        self._messages = messages
        return self

    def __aiter__(self):
        self._tokens = ["fake", " ", "token"]
        self._index = 0
        return self

    async def __anext__(self):
        if self._index < len(self._tokens):
            token = self._tokens[self._index]
            self._index += 1
            return type("Chunk", (), {"content": token})()
        raise StopAsyncIteration


@pytest.fixture
def fake_chat_ollama(monkeypatch):
    monkeypatch.setattr(
        "chat.services.ChatOllama",
        FakeChatOllama,
    )


@pytest.mark.asyncio
async def test_service_streams_chunks(fake_chat_ollama):
    service = OllamaChatService(base_url="http://test:11434", model="test-model")
    chunks = []
    async for token in service.stream([{"role": "user", "content": "hi"}]):
        chunks.append(token)
    assert chunks == ["fake", " ", "token"]
