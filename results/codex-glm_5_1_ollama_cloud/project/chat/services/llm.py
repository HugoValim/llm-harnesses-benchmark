"""LLM service module — thin wrapper around langchain-ollama ChatOllama."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import httpx
from langchain_core.messages import AIMessage, HumanMessage
from langchain_ollama import ChatOllama

OLLAMA_HOST_DEFAULT = "http://localhost:11434"
OLLAMA_MODEL_DEFAULT = "qwen2.5:7b"


def _ollama_host() -> str:
    return os.environ.get("OLLAMA_HOST", OLLAMA_HOST_DEFAULT)


def _ollama_model() -> str:
    return os.environ.get("OLLAMA_MODEL", OLLAMA_MODEL_DEFAULT)


def get_llm_client() -> ChatOllama:
    """Return a ChatOllama instance configured from environment variables."""
    return ChatOllama(
        model=_ollama_model(),
        base_url=_ollama_host(),
        async_client_kwargs={
            "timeout": httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0),
        },
    )


async def stream_response(
    messages: list[dict[str, str]],
) -> AsyncIterator[str]:
    """Stream tokens from the LLM given a conversation history.

    Parameters
    ----------
    messages:
        List of {"role": "human"|"ai", "content": "..."} dicts.

    Yields
    ------
    str
        Each content token as it arrives from the model.
    """
    client = get_llm_client()
    lc_messages: list[HumanMessage | AIMessage] = []
    for msg in messages:
        if msg["role"] == "human":
            lc_messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "ai":
            lc_messages.append(AIMessage(content=msg["content"]))
        else:
            raise ValueError(f"Unknown role: {msg['role']!r}")

    async for chunk in client.astream(lc_messages):
        if isinstance(chunk.content, str) and chunk.content:
            yield chunk.content
