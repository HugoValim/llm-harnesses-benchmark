"""HTTP views for chat UI and Ollama health."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from chat.services import llm


def chat_index(request: HttpRequest) -> HttpResponse:
    """Render the ChatGPT-style single-page chat interface."""
    return render(request, "chat/index.html")


@require_GET
def ollama_health(request: HttpRequest) -> JsonResponse:
    """Report Ollama reachability without exposing secrets."""
    reachable, detail = llm.check_ollama_reachable()
    payload = {
        "reachable": reachable,
        "detail": detail,
        "configured_model": settings.OLLAMA_MODEL,
        "configured_host": settings.OLLAMA_HOST,
    }
    status = 200 if reachable else 503
    return JsonResponse(payload, status=status, json_dumps_params={"indent": 2})
