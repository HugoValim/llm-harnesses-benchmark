"""
LLM service using LangChain Ollama for streaming chat.
"""

import os
from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama


class LLMService:
    """Service for interacting with Ollama via LangChain."""

    def __init__(self) -> None:
        ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        ollama_model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")

        self.client = ChatOllama(
            model=ollama_model,
            base_url=ollama_host,
        )
        self.conversation_history: list[dict[str, Any]] = []

    async def stream_response(
        self,
        message: str,
        system_prompt: str | None = None,
    ) -> AsyncGenerator[str]:
        """Stream response tokens from the LLM."""
        messages: list[Any] = []

        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))

        for msg in self.conversation_history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))

        messages.append(HumanMessage(content=message))

        try:
            async for chunk in self.client.astream(messages):
                if hasattr(chunk, "content") and chunk.content:
                    yield chunk.content
                elif isinstance(chunk, str):
                    yield chunk

            self.conversation_history.append({"role": "user", "content": message})
        except Exception as e:
            raise ConnectionError(f"Failed to stream from Ollama: {e}") from e

    async def health_check(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            async for _ in self.client.astream([HumanMessage(content="ping")]):
                return True
            return True
        except Exception:
            return False

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.conversation_history.clear()
