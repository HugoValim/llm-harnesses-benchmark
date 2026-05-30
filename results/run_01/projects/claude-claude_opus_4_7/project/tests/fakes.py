"""Named test doubles for the LLM service boundary.

Tests inject :class:`FakeChatService` in place of
``chat.services.OllamaChatService`` so no real Ollama/LangChain call is made.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence

from chat.services import ChatTurn


class FakeChatService:
    """Stand-in for ``OllamaChatService`` with scripted streaming behaviour."""

    def __init__(
        self,
        tokens: Sequence[str] | None = None,
        *,
        error: Exception | None = None,
        healthy: bool = True,
        model: str = "fake-model",
        per_token_delay: float = 0.0,
    ) -> None:
        self.tokens: list[str] = list(tokens) if tokens is not None else ["Hel", "lo", " wor", "ld"]
        self.error = error
        self.healthy = healthy
        self.model = model
        self.per_token_delay = per_token_delay
        self.received_history: list[ChatTurn] = []

    async def astream_reply(self, history: Sequence[ChatTurn]) -> AsyncIterator[str]:
        self.received_history = list(history)
        if self.error is not None:
            raise self.error
        for token in self.tokens:
            if self.per_token_delay:
                await asyncio.sleep(self.per_token_delay)
            yield token

    async def check_health(self, *, timeout_seconds: float = 3.0) -> bool:
        return self.healthy
