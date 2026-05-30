import asyncio
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

from langchain_ollama import ChatOllama

logger = logging.getLogger(__name__)

OLLAMA_HOST: str = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


def _build_llm() -> ChatOllama:
    return ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_HOST,
        temperature=0.7,
    )


async def stream_response(messages: list[dict[str, str]]) -> AsyncIterator[str]:
    llm = _build_llm()
    try:
        async for chunk in llm.astream(messages):
            content: Any = chunk.content
            if content:
                yield str(content)
    except Exception as e:
        msg: str = (
            f"\n\n**Error**: Unable to reach Ollama at {OLLAMA_HOST}. "
            f"Verify the service is running and {OLLAMA_MODEL} is pulled."
        )
        logger.error("Ollama stream failed: %s", e)
        yield msg
        raise


async def check_ollama_health() -> str:
    try:
        llm = _build_llm()
        await asyncio.wait_for(llm.ainvoke(["hello"]), timeout=5.0)
        return "ok"
    except Exception as e:
        logger.warning("Ollama health check failed: %s", e)
        return f"unreachable: {e}"
