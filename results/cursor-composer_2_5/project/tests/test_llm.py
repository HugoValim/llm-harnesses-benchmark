"""LangChain service tests with a named fake model."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from chat.services import llm
from langchain_core.messages import AIMessage, HumanMessage
from tests.fakes import FakeStreamingChatModel


@pytest.mark.asyncio
async def test_stream_chat_tokens_yields_multiple_chunks() -> None:
    fake = FakeStreamingChatModel(tokens=("alpha", "beta", "gamma"))
    history: list = []
    with patch("chat.services.llm.build_chat_model", return_value=fake):
        chunks = [token async for token in llm.stream_chat_tokens(history, "Hi")]
    assert chunks == ["alpha", "beta", "gamma"]
    assert fake.last_messages is not None
    assert isinstance(fake.last_messages[-1], HumanMessage)


def test_append_turn_extends_history() -> None:
    history: list = []
    llm.append_turn(history, "Question?", "Answer.")
    assert len(history) == 2
    assert isinstance(history[0], HumanMessage)
    assert isinstance(history[1], AIMessage)


def test_check_ollama_reachable_success() -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    with patch("httpx.get", return_value=FakeResponse()):
        ok, detail = llm.check_ollama_reachable()
    assert ok is True
    assert detail == "ok"
