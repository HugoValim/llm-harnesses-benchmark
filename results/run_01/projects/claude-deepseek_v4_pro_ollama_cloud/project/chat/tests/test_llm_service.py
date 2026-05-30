from collections.abc import AsyncIterator

import pytest

from chat.llm_service import LLMService


class FakeChunk:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeChatOllama:
    """Named fake class for ChatOllama used in tests."""

    def __init__(self, chunks: list[str] | None = None) -> None:
        self._chunks = chunks or ["Hello", " world", "!"]

    async def astream(self, messages: list[dict[str, str]]) -> AsyncIterator[FakeChunk]:
        for text in self._chunks:
            yield FakeChunk(content=text)


@pytest.mark.asyncio
async def test_stream_yields_multiple_chunks() -> None:
    svc = LLMService()
    svc._build_client = lambda: FakeChatOllama(chunks=["chunk1", "chunk2", "chunk3"])  # type: ignore[assignment,return-value]
    results = []
    async for token in svc.stream([{"role": "user", "content": "hi"}]):
        results.append(token)
    assert len(results) == 3
    assert results == ["chunk1", "chunk2", "chunk3"]


@pytest.mark.asyncio
async def test_stream_skips_empty_content() -> None:
    svc = LLMService()
    svc._build_client = lambda: FakeChatOllama(chunks=["a", "", "b"])  # type: ignore[assignment,return-value]
    results = []
    async for token in svc.stream([{"role": "user", "content": "hi"}]):
        results.append(token)
    assert results == ["a", "b"]


@pytest.mark.asyncio
async def test_stream_passes_messages_to_client() -> None:
    messages_sent = []

    class CapturingFake(FakeChatOllama):
        async def astream(self, messages: list[dict[str, str]]) -> AsyncIterator[FakeChunk]:
            messages_sent.extend(messages)
            yield FakeChunk(content="ok")

    svc = LLMService()
    svc._build_client = lambda: CapturingFake()  # type: ignore[assignment,return-value]
    msgs = [{"role": "user", "content": "hello"}]
    async for _ in svc.stream(msgs):
        pass
    assert messages_sent == msgs


@pytest.mark.asyncio
async def test_check_health_reachable() -> None:
    svc = LLMService()
    svc._build_client = lambda: FakeChatOllama(chunks=["ok"])  # type: ignore[assignment,return-value]
    result = await svc.check_health()
    assert result["reachable"] is True
    assert result["model"] == svc.model


@pytest.mark.asyncio
async def test_check_health_unreachable() -> None:
    svc = LLMService()

    class FailingFake:
        async def astream(self, messages: list[dict[str, str]]) -> AsyncIterator[FakeChunk]:
            raise ConnectionError("refused")
            yield

    svc._build_client = lambda: FailingFake()  # type: ignore[assignment,return-value]
    result = await svc.check_health()
    assert result["reachable"] is False
    assert "error" in result
