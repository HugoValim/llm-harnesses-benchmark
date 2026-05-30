from __future__ import annotations

import pytest
from langchain_core.messages import BaseMessage

from chat import llm_service
from chat.tests.fakes import FakeChatOllamaClient


@pytest.mark.asyncio
async def test_stream_assistant_tokens_yields_multiple_chunks_and_updates_history() -> None:
    fake = FakeChatOllamaClient(["aa", "bb", "cc"])
    history: list[BaseMessage] = []
    chunks: list[str] = []
    async for token in llm_service.stream_assistant_tokens(history, "hi", llm=fake):
        chunks.append(token)
    assert chunks == ["aa", "bb", "cc"]
    assert len(history) == 2
