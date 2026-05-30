from __future__ import annotations

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from chat.ollama_health import ollama_reachable_sync


@require_GET
def chat_spa(request: HttpRequest) -> HttpResponse:
    return render(request, "chat/spa.html")


@require_GET
def health(request: HttpRequest) -> HttpResponse:
    ok, err = ollama_reachable_sync()
    return JsonResponse({"status": "ok" if ok else "degraded", "ollama": {"ok": ok, "error": err}})


@require_GET
def health_live(request: HttpRequest) -> HttpResponse:
    """Minimal liveness probe (Django up)."""
    return HttpResponse("ok", content_type="text/plain")
