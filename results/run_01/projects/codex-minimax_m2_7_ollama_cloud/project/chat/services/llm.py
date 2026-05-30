"""Ollama LLM service with streaming support."""

from collections.abc import AsyncIterator
from typing import Any

from django.conf import settings
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_ollama import ChatOllama


class OllamaConnectionError(Exception):
    """Raised when Ollama server is unreachable."""

    def __init__(self, host: str, message: str = "") -> None:
        self.host = host
        super().__init__(f"Cannot connect to Ollama at {host}. {message}")


class ChatService:
    """Streaming chat service backed by ChatOllama."""

    def __init__(self) -> None:
        self._client: ChatOllama | None = None
        self._history: list[BaseMessage] = []

    @property
    def client(self) -> ChatOllama:
        if self._client is None:
            self._client = ChatOllama(
                base_url=settings.OLLAMA_HOST,
                model=settings.OLLAMA_MODEL,
            )
        return self._client

    def reset_history(self) -> None:
        self._history.clear()

    def _extract_content(self, chunk: Any) -> str:
        """Extract string content from a LangChain chunk."""
        if hasattr(chunk, "content"):
            raw = chunk.content
            if isinstance(raw, str):
                return raw
            if isinstance(raw, list):
                parts: list[str] = []
                for part in raw:
                    if isinstance(part, str):
                        parts.append(part)
                    elif isinstance(part, dict) and "text" in part:
                        parts.append(str(part["text"]))
                return "".join(parts)
        return str(chunk)

    async def astream_tokens(self, prompt: str) -> AsyncIterator[str]:
        """Stream tokens from Ollama, maintaining conversation history."""
        self._history.append(HumanMessage(content=prompt))
        try:
            async for chunk in self.client.astream(self._history):
                content = self._extract_content(chunk)
                if content:
                    yield content
                if isinstance(chunk, AIMessage):
                    self._history.append(chunk)
        except Exception as e:
            if self._history:
                self._history.pop()
            raise OllamaConnectionError(settings.OLLAMA_HOST, str(e)) from e

    async def astream_tokens_simple(self, prompt: str) -> AsyncIterator[str]:
        """Stream tokens without conversation history (single-turn)."""
        try:
            async for chunk in self.client.astream([HumanMessage(content=prompt)]):
                content = self._extract_content(chunk)
                if content:
                    yield content
        except Exception as e:
            raise OllamaConnectionError(settings.OLLAMA_HOST, str(e)) from e
