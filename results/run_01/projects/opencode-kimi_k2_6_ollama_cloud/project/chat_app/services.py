"""LLM service wrapping ChatOllama."""

from collections.abc import AsyncIterator
from typing import Any

from django.conf import settings
from langchain_ollama import ChatOllama


class LlmStreamer:
    """Stream tokens from Ollama via ChatOllama."""

    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        self.model = model or settings.OLLAMA_MODEL
        self.base_url = base_url or settings.OLLAMA_HOST

    async def astream(self, messages: list[dict[str, Any]]) -> AsyncIterator[str]:
        """Yield token strings from Ollama for the given messages."""
        client = ChatOllama(
            model=self.model,
            base_url=self.base_url,
        )
        async for chunk in client.astream(messages):
            text = chunk.content if hasattr(chunk, "content") else str(chunk)
            if isinstance(text, str) and text:
                yield text
