"""
LangChain Ollama client wiring. Production code uses ChatOllama only.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Protocol, cast

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage
from langchain_ollama import ChatOllama


class OllamaStreamClient(Protocol):
    """Minimal protocol implemented by `ChatOllama` and test doubles."""

    def astream(self, messages: object) -> AsyncIterator[AIMessageChunk]: ...


def build_chat_ollama() -> ChatOllama:
    """Construct ChatOllama from environment (OLLAMA_HOST, OLLAMA_MODEL)."""
    base_url = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
    return ChatOllama(model=model, base_url=base_url)


async def stream_assistant_tokens(
    history: list[BaseMessage],
    user_text: str,
    *,
    llm: OllamaStreamClient | None = None,
) -> AsyncIterator[str]:
    """
    Stream assistant tokens for a new user turn, mutating `history` on success.

    Yields decoded token strings. On completion appends HumanMessage + AIMessage.
    Does not mutate history if streaming fails before completion.
    """
    client: OllamaStreamClient = cast(OllamaStreamClient, llm or build_chat_ollama())
    user_msg = HumanMessage(content=user_text)
    messages = [*history, user_msg]
    collected = ""
    async for chunk in client.astream(messages):
        if not isinstance(chunk, AIMessageChunk) or not chunk.content:
            continue
        piece = chunk.content
        if not isinstance(piece, str):
            continue
        collected += piece
        yield piece
    history.append(user_msg)
    history.append(AIMessage(content=collected))
