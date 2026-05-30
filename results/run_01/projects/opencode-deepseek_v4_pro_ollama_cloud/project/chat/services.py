import logging
from collections.abc import AsyncGenerator

from django.conf import settings
from langchain_ollama import ChatOllama

logger = logging.getLogger(__name__)


def build_chat_ollama() -> ChatOllama:
    return ChatOllama(
        model=settings.OLLAMA_MODEL,
        base_url=settings.OLLAMA_HOST,
    )


async def check_ollama_reachability() -> bool:
    try:
        client = build_chat_ollama()
        await client.ainvoke("ping")
        return True
    except Exception:
        logger.exception("Ollama reachability check failed")
        return False


async def stream_response(
    messages: list[dict[str, str]],
) -> AsyncGenerator[str]:
    client = build_chat_ollama()
    async for chunk in client.astream(messages):
        content = chunk.content
        if isinstance(content, str) and content:
            yield content
