"""Unit tests for the Ollama LLM service boundary."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from chat import services
from chat.services import (
    ChatTurn,
    OllamaChatService,
    OllamaUnavailableError,
    _chunk_text,
    create_chat_service,
)


class FakeAIChunk:
    """Mimics a LangChain message chunk carrying partial content."""

    def __init__(self, content: str | list[str | dict[str, object]]) -> None:
        self.content = content


class FakeStreamingClient:
    """Replaces the internal ChatOllama client with scripted output."""

    def __init__(self, chunks: list[FakeAIChunk], *, error: Exception | None = None) -> None:
        self._chunks = chunks
        self._error = error
        self.seen_messages: object | None = None

    async def astream(self, messages: object) -> AsyncIterator[FakeAIChunk]:
        self.seen_messages = messages
        if self._error is not None:
            raise self._error
        for chunk in self._chunks:
            yield chunk


def test_chunk_text_passes_through_plain_strings() -> None:
    assert _chunk_text("hello") == "hello"


def test_chunk_text_flattens_structured_content() -> None:
    content: list[str | dict[str, object]] = ["a", {"text": "b"}, {"other": "skip"}]
    assert _chunk_text(content) == "ab"


def test_build_messages_prepends_system_and_maps_roles() -> None:
    service = OllamaChatService(model="m", base_url="http://x")
    history = [ChatTurn("human", "hi"), ChatTurn("ai", "hello")]

    messages = service._build_messages(history)

    assert [type(m).__name__ for m in messages] == [
        "SystemMessage",
        "HumanMessage",
        "AIMessage",
    ]
    assert messages[1].content == "hi"
    assert messages[2].content == "hello"


async def test_astream_reply_yields_multiple_tokens() -> None:
    service = OllamaChatService(model="m", base_url="http://x")
    service._client = FakeStreamingClient([FakeAIChunk("Hel"), FakeAIChunk(""), FakeAIChunk("lo")])  # type: ignore[assignment]

    tokens = [token async for token in service.astream_reply([ChatTurn("human", "hi")])]

    assert tokens == ["Hel", "lo"]  # empty chunk filtered out, order preserved


async def test_astream_reply_wraps_backend_errors() -> None:
    service = OllamaChatService(model="m", base_url="http://x")
    service._client = FakeStreamingClient([], error=RuntimeError("connection refused"))  # type: ignore[assignment]

    with pytest.raises(OllamaUnavailableError) as excinfo:
        async for _ in service.astream_reply([ChatTurn("human", "hi")]):
            pass

    assert "connection refused" in str(excinfo.value)


async def test_check_health_false_when_host_unreachable() -> None:
    service = OllamaChatService(model="m", base_url="http://localhost:1")
    assert await service.check_health(timeout_seconds=0.5) is False


async def test_check_health_true_when_host_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        status_code = 200

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, url: str) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr(services.httpx, "AsyncClient", FakeAsyncClient)
    service = OllamaChatService(model="m", base_url="http://ollama:11434")
    assert await service.check_health() is True


def test_env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    assert services.get_ollama_host() == "http://localhost:11434"
    assert services.get_ollama_model() == "qwen2.5:7b"


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://example:1234")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3:8b")
    service = create_chat_service()
    assert isinstance(service, OllamaChatService)
    assert service.base_url == "http://example:1234"
    assert service.model == "llama3:8b"
