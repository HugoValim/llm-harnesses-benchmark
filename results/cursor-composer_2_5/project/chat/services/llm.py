"""LangChain Ollama client and streaming helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
from django.conf import settings
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    BaseMessageChunk,
    HumanMessage,
)
from langchain_ollama import ChatOllama


def build_chat_model() -> ChatOllama:
    """Construct the project ChatOllama client from environment settings."""
    return ChatOllama(
        model=settings.OLLAMA_MODEL,
        base_url=settings.OLLAMA_HOST,
    )


def check_ollama_reachable() -> tuple[bool, str]:
    """Return whether the configured Ollama host responds to a tags probe."""
    tags_url = f"{settings.OLLAMA_HOST.rstrip('/')}/api/tags"
    try:
        response = httpx.get(tags_url, timeout=5.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return False, f"Ollama unreachable at {settings.OLLAMA_HOST}: {exc}"
    return True, "ok"


async def stream_chat_tokens(
    history: list[BaseMessage],
    user_text: str,
) -> AsyncIterator[str]:
    """Stream assistant tokens for a user turn via ChatOllama.astream."""
    messages: list[BaseMessage] = [*history, HumanMessage(content=user_text)]
    model = build_chat_model()
    async for chunk in model.astream(messages):
        token = _chunk_text(chunk)
        if token:
            yield token


def _chunk_text(chunk: BaseMessageChunk | AIMessage) -> str:
    content = chunk.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def append_turn(
    history: list[BaseMessage],
    user_text: str,
    assistant_text: str,
) -> None:
    """Record a completed exchange in the in-memory history."""
    history.append(HumanMessage(content=user_text))
    history.append(AIMessage(content=assistant_text))
