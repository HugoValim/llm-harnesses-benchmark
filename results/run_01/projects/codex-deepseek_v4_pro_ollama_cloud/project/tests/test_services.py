"""Tests for the LLM service module — mocks langchain_ollama layer."""

from unittest.mock import patch

import pytest

from chat.services import LLMError, stream_chat


class FakeChunk:
    """Fake langchain chunk with content attribute."""

    def __init__(self, content: str) -> None:
        self.content = content


async def _fake_astream(_messages):
    """Yield multiple fake chunks to prove streaming is exercised."""
    for token in ["Hello", ", ", "world", "!"]:
        yield FakeChunk(token)


class TestStreamChat:
    """stream_chat forwards tokens from ChatOllama.astream."""

    @pytest.mark.asyncio
    async def test_yields_multiple_chunks(self) -> None:
        with patch("chat.services.ChatOllama") as mock_client_cls:
            mock_client_cls.return_value.astream = _fake_astream
            chunks = []
            async for chunk in stream_chat([{"role": "user", "content": "hi"}]):
                chunks.append(chunk)
            assert chunks == ["Hello", ", ", "world", "!"]

    @pytest.mark.asyncio
    async def test_raises_llm_error_on_failure(self) -> None:
        def _failing_astream(*_args, **_kw):
            raise ConnectionError("boom")

        with patch("chat.services.ChatOllama") as mock_client_cls:
            mock_client_cls.return_value.astream = _failing_astream
            with pytest.raises(LLMError) as exc_info:
                async for _ in stream_chat([{"role": "user", "content": "hi"}]):
                    pass
            assert "boom" in str(exc_info.value)
