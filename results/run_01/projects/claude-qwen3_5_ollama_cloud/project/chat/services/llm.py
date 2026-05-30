"""
LLM service - wraps ChatOllama for streaming responses.
"""

import logging
import os
from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_ollama import ChatOllama

logger = logging.getLogger(__name__)

# Environment-driven configuration - no hardcoded secrets
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


class LLMService:
    """
    Service for streaming LLM responses via Ollama + LangChain.

    Maintains conversation context and streams tokens as they arrive.
    """

    def __init__(self, host: str | None = None, model: str | None = None):
        self.host = host or OLLAMA_HOST
        self.model = model or OLLAMA_MODEL
        self._client: ChatOllama | None = None

    @property
    def client(self) -> ChatOllama:
        """Lazy-load the ChatOllama client."""
        if self._client is None:
            self._client = ChatOllama(
                model=self.model,
                base_url=self.host,
            )
        return self._client

    async def stream_response(
        self,
        messages: list[dict[str, str]],
    ) -> AsyncGenerator[str, None]:
        """
        Stream tokens from Ollama for the given conversation history.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
                     Roles: 'human', 'ai', 'system'

        Yields:
            Token strings as they arrive from the model.

        Raises:
            ConnectionError: If Ollama is unreachable.
            RuntimeError: If streaming fails.
        """
        # Convert to LangChain message types
        lc_messages: list[BaseMessage] = []
        for msg in messages:
            role = msg.get("role", "human").lower()
            content = msg.get("content", "")
            if role in ("human", "user"):
                lc_messages.append(HumanMessage(content=content))
            elif role == "ai":
                lc_messages.append(AIMessage(content=content))
            else:
                # Treat unknown roles as human messages
                lc_messages.append(HumanMessage(content=content))

        logger.debug(f"Streaming response for {len(lc_messages)} messages")

        try:
            async for chunk in self.client.astream(lc_messages):
                # Extract content from chunk - handle different chunk formats
                token_content: str = ""
                if hasattr(chunk, "content"):
                    val = chunk.content
                    token_content = str(val) if not isinstance(val, str) else val
                elif isinstance(chunk, dict) and "content" in chunk:
                    token_content = str(chunk["content"])

                if token_content:
                    yield token_content
        except Exception as e:
            error_msg = str(e)
            logger.error(f"LLM streaming failed: {error_msg}")
            # Surface connection errors clearly
            if "connection" in error_msg.lower() or "refused" in error_msg.lower():
                raise ConnectionError(
                    f"Cannot connect to Ollama at {self.host}. "
                    "Ensure Ollama is running and the model is pulled."
                ) from e
            raise RuntimeError(f"LLM streaming failed: {error_msg}") from e

    async def health_check(self) -> dict[str, Any]:
        """
        Check if Ollama is reachable and the model is available.

        Returns:
            Dict with 'healthy', 'host', 'model', and optional 'error' keys.
        """
        try:
            # Try a minimal request to check connectivity
            test_messages = [{"role": "human", "content": "."}]
            # Use astream but just check we can iterate
            async for _ in self.stream_response(test_messages):
                break  # Got at least one token - connection works
            return {
                "healthy": True,
                "host": self.host,
                "model": self.model,
            }
        except ConnectionError as e:
            return {
                "healthy": False,
                "host": self.host,
                "model": self.model,
                "error": str(e),
            }
        except Exception as e:
            return {
                "healthy": False,
                "host": self.host,
                "model": self.model,
                "error": f"Health check failed: {str(e)}",
            }


# Singleton instance for use across the application
_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    """Get or create the singleton LLM service instance."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
