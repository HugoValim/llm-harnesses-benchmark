from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from langchain_core.messages import AIMessageChunk


class FakeChatOllamaClient:
    """
    Test double for `ChatOllama` streaming.

    Mimics the async iterator contract used by `chat.llm_service.stream_assistant_tokens`.
    """

    def __init__(self, parts: Sequence[str] | None = None) -> None:
        self.parts: tuple[str, ...] = tuple(parts) if parts is not None else ("Hel", "lo", "!")

    def astream(self, messages: object) -> AsyncIterator[AIMessageChunk]:  # noqa: ARG002
        parts = self.parts

        async def _gen() -> AsyncIterator[AIMessageChunk]:
            for part in parts:
                yield AIMessageChunk(content=part)

        return _gen()
