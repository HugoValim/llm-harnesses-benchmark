"""LLM service — thin wrapper around langchain_ollama.ChatOllama.

Owns the only import path for langchain_ollama in production code.
Tests fake this module's public interface.
"""

import os
from collections.abc import AsyncIterator
from typing import Any

from langchain_ollama import ChatOllama


class LLMError(Exception):
    """Raised when the LLM is unreachable or streaming fails."""


def _build_client() -> ChatOllama:
    base_url = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
    return ChatOllama(base_url=base_url, model=model)


async def check_ollama_health() -> dict[str, Any]:
    """Preflight: ping Ollama and return status."""
    try:
        client = _build_client()
        await client.ainvoke("ping")
        return {"reachable": True, "model": client.model}
    except Exception as exc:
        return {"reachable": False, "error": str(exc)}


async def stream_chat(
    messages: list[dict[str, str]],
) -> AsyncIterator[str]:
    """Stream tokens from Ollama -> caller yields each content chunk.

    Args:
        messages: List of {"role": "user"|"assistant", "content": str}.

    Yields:
        str chunks as they arrive from the model stream.

    Raises:
        LLMError: on transport or model-level failure.
    """
    try:
        client = _build_client()
        async for chunk in client.astream(messages):
            content: str = getattr(chunk, "content", "")
            if content:
                yield content
    except Exception as exc:
        raise LLMError(f"LLM stream failed: {exc}") from exc
