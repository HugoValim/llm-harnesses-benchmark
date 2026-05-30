"""Views for chat app."""

import asyncio
import urllib.parse

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render


def chat_page(request: HttpRequest) -> HttpResponse:
    return render(request, "chat_app/chat.html")


async def health(request: HttpRequest) -> JsonResponse:
    parsed = urllib.parse.urlparse(settings.OLLAMA_HOST)
    host = parsed.hostname or "localhost"
    port = parsed.port or 11434
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=2,
        )
        writer.close()
        await writer.wait_closed()
        reachable = True
    except Exception:  # noqa: BLE001
        reachable = False
    return JsonResponse(
        {
            "ollama_reachable": reachable,
            "model": settings.OLLAMA_MODEL,
        },
    )
