"""Test doubles for the LangChain streaming boundary."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

from langchain_core.messages import AIMessageChunk, BaseMessage


class FakeStreamingChatModel:
    """Named fake that yields multiple AIMessageChunk tokens from astream."""

    def __init__(self, tokens: Sequence[str] | None = None) -> None:
        self._tokens = list(tokens or ("Hello", ", ", "world"))
        self.last_messages: list[BaseMessage] | None = None

    async def astream(self, messages: list[BaseMessage]) -> AsyncIterator[AIMessageChunk]:
        self.last_messages = list(messages)
        for token in self._tokens:
            yield AIMessageChunk(content=token)

    def bind(self, **_kwargs: Any) -> FakeStreamingChatModel:
        return self
