from collections.abc import AsyncGenerator

import httpx
from django.conf import settings
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama


def get_chat_model() -> ChatOllama:
    return ChatOllama(
        model=settings.OLLAMA_MODEL,
        base_url=settings.OLLAMA_HOST,
    )


async def stream_response(
    messages: list[dict[str, str]],
) -> AsyncGenerator[str]:
    model = get_chat_model()
    lc_messages: list[SystemMessage | HumanMessage] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        else:
            lc_messages.append(HumanMessage(content=content))

    async for chunk in model.astream(lc_messages):
        text = chunk.content
        if isinstance(text, str) and text:
            yield text


async def check_ollama_health() -> dict[str, str | bool]:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{settings.OLLAMA_HOST}/api/tags", timeout=5.0)
            resp.raise_for_status()
            return {"reachable": True, "host": settings.OLLAMA_HOST}
    except Exception as exc:
        return {"reachable": False, "host": settings.OLLAMA_HOST, "error": str(exc)}
