import os
from collections.abc import AsyncIterator

from langchain_ollama import ChatOllama


class OllamaChatService:
    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        self.base_url = base_url or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.model = model or os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
        self._client: ChatOllama | None = None

    def _get_client(self) -> ChatOllama:
        if self._client is None:
            self._client = ChatOllama(
                model=self.model,
                base_url=self.base_url,
            )
        return self._client

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        client = self._get_client()
        langchain_messages = [(m["role"], m["content"]) for m in messages]
        async for chunk in client.astream(langchain_messages):
            raw = chunk.content if hasattr(chunk, "content") else str(chunk)
            content = raw if isinstance(raw, str) else str(raw)
            if content:
                yield content
