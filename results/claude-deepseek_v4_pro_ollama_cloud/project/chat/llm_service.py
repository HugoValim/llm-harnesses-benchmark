import os
from collections.abc import AsyncIterator
from typing import Any

from langchain_ollama import ChatOllama


class LLMService:
    """Thin wrapper around ChatOllama for streaming chat completions."""

    def __init__(self) -> None:
        self.host: str = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.model: str = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")

    def _build_client(self) -> ChatOllama:
        return ChatOllama(model=self.model, base_url=self.host)

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        """Stream token chunks from Ollama via LangChain.

        Args:
            messages: List of {"role": "user|assistant|system", "content": "..."} dicts.

        Yields:
            Content string chunks as they arrive from the model.
        """
        client = self._build_client()
        async for chunk in client.astream(messages):
            content = chunk.content
            if isinstance(content, str) and content:
                yield content

    async def check_health(self) -> dict[str, Any]:
        """Check Ollama reachability without exposing secrets.

        Returns:
            Dict with "reachable" bool and "model" string.
        """
        try:
            client = self._build_client()
            async for _chunk in client.astream([{"role": "user", "content": "ping"}]):
                content = _chunk.content
                if isinstance(content, str) and content:
                    break
            return {"reachable": True, "model": self.model}
        except Exception as exc:
            return {"reachable": False, "model": self.model, "error": str(exc)}
