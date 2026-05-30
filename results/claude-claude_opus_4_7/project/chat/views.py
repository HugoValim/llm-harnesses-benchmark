"""HTTP views: the chat SPA shell and an Ollama health probe."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from chat.services import create_chat_service


def index(request: HttpRequest) -> HttpResponse:
    """Render the single-page chat UI."""
    return render(request, "chat/index.html")


async def health(request: HttpRequest) -> JsonResponse:
    """Report Ollama reachability without leaking any secret values."""
    service = create_chat_service()
    reachable = await service.check_health()
    return JsonResponse(
        {
            "status": "ok" if reachable else "degraded",
            "ollama_reachable": reachable,
            "model": service.model,
        },
        status=200 if reachable else 503,
    )
