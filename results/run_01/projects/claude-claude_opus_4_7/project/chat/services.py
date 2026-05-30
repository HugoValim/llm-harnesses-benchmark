"""LLM service boundary wrapping ``langchain_ollama.ChatOllama``.

This module is the *only* place the application talks to the model. The
WebSocket consumer depends on :class:`OllamaChatService` through
:func:`create_chat_service`, which tests replace with a fake. Production code
never imports the raw ``ollama`` package.

Example:
    >>> service = create_chat_service()
    >>> async for token in service.astream_reply([ChatTurn("human", "hi")]):
    ...     print(token, end="")
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal

import httpx
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant. Answer clearly and concisely."

Role = Literal["system", "human", "ai"]


@dataclass(frozen=True, slots=True)
class ChatTurn:
    """A single turn in a conversation."""

    role: Role
    content: str


def get_ollama_host() -> str:
    """Return the Ollama base URL from ``OLLAMA_HOST`` (env-driven, not secret)."""
    return os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)


def get_ollama_model() -> str:
    """Return the Ollama model tag from ``OLLAMA_MODEL`` (env-driven, not secret)."""
    return os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)


def _chunk_text(content: str | list[str | dict[str, object]]) -> str:
    """Coerce a LangChain message chunk's content into plain text."""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for piece in content:
        if isinstance(piece, str):
            parts.append(piece)
        elif isinstance(piece, dict):
            value = piece.get("text", "")
            if isinstance(value, str):
                parts.append(value)
    return "".join(parts)


class OllamaChatService:
    """Streams chat completions from Ollama through LangChain.

    Args:
        model: Override for the model tag; defaults to ``OLLAMA_MODEL``.
        base_url: Override for the host URL; defaults to ``OLLAMA_HOST``.
        system_prompt: Leading system instruction for every conversation.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> None:
        self.model = model or get_ollama_model()
        self.base_url = base_url or get_ollama_host()
        self._system_prompt = system_prompt
        self._client = ChatOllama(model=self.model, base_url=self.base_url)

    def _build_messages(self, history: Sequence[ChatTurn]) -> list[BaseMessage]:
        messages: list[BaseMessage] = [SystemMessage(content=self._system_prompt)]
        for turn in history:
            if turn.role == "human":
                messages.append(HumanMessage(content=turn.content))
            elif turn.role == "ai":
                messages.append(AIMessage(content=turn.content))
            else:
                messages.append(SystemMessage(content=turn.content))
        return messages

    async def astream_reply(self, history: Sequence[ChatTurn]) -> AsyncIterator[str]:
        """Yield reply tokens as they stream from the model.

        Raises:
            OllamaUnavailableError: If the model cannot be reached or streaming
                fails partway through.
        """
        messages = self._build_messages(history)
        try:
            async for chunk in self._client.astream(messages):
                text = _chunk_text(chunk.content)
                if text:
                    yield text
        except Exception as exc:
            raise OllamaUnavailableError(
                f"streaming from Ollama model {self.model!r} at {self.base_url!r} failed: {exc}"
            ) from exc

    async def check_health(self, *, timeout_seconds: float = 3.0) -> bool:
        """Return whether the Ollama host answers, without exposing secrets."""
        url = self.base_url.rstrip("/") + "/api/tags"
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.get(url)
            return response.status_code == httpx.codes.OK
        except httpx.HTTPError:
            return False


class OllamaUnavailableError(RuntimeError):
    """Raised when the Ollama backend is unreachable or a stream fails."""


def create_chat_service() -> OllamaChatService:
    """Factory used by the consumer; patched in tests to inject a fake."""
    return OllamaChatService()
