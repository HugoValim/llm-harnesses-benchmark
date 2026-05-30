"""
LLM service for streaming responses from Ollama.
"""

import os
from collections.abc import AsyncIterator

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_ollama import ChatOllama


class OllamaService:
    """Streams chat completions from Ollama via LangChain."""

    def __init__(self) -> None:
        self.host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
        self._client: ChatOllama | None = None

    @property
    def client(self) -> ChatOllama:
        if self._client is None:
            self._client = ChatOllama(model=self.model, base_url=self.host)
        return self._client

    async def stream_chat(
        self, messages: list[BaseMessage]
    ) -> AsyncIterator[str]:
        """Stream chat response chunks from Ollama."""
        async for chunk in self.client.astream(messages):
            if chunk.content:
                yield chunk.content

    def health_check(self) -> dict:
        """Check if Ollama is reachable."""
        try:
            self.client.invoke([HumanMessage(content="ping")])
            return {"status": "ok", "host": self.host, "model": self.model}
        except Exception as e:
            return {"status": "error", "host": self.host, "model": self.model, "error": str(e)}


ollama_service = OllamaService()
