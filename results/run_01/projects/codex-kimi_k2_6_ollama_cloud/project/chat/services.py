import logging
import os
from collections.abc import AsyncIterator
from typing import cast

import httpx
from langchain_ollama import ChatOllama

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


def build_client() -> ChatOllama:
    return ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_HOST)


def ollama_reachable() -> bool:
    try:
        resp = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


async def stream_reply(history: list[dict[str, str]]) -> AsyncIterator[str]:
    client = build_client()
    messages = [(m["role"], m["content"]) for m in history]
    try:
        async for chunk in client.astream(messages):
            if hasattr(chunk, "content"):
                content = cast(str, chunk.content)
            else:
                content = str(chunk)
            if content:
                yield content
    except Exception as exc:
        logger.exception("streaming failed")
        yield f"\n[Error: {exc}]"
