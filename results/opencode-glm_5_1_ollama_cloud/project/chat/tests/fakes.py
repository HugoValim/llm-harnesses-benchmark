from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessageChunk


class FakeChatOllama:
    def __init__(self, chunks: list[str] | None = None, *, should_error: bool = False):
        self._chunks = chunks or ["Hello", " world", "!"]
        self._should_error = should_error
        self.call_count = 0
        self.received_messages: list[list[dict]] = []

    async def astream(self, messages: list) -> AsyncGenerator[AIMessageChunk]:
        self.call_count += 1
        self.received_messages.append(
            [
                {"role": "user" if hasattr(m, "type") else "unknown", "content": str(m)}
                for m in messages
            ]
        )
        if self._should_error:
            raise ConnectionError("Ollama unreachable")
        for chunk_text in self._chunks:
            yield AIMessageChunk(content=chunk_text)
