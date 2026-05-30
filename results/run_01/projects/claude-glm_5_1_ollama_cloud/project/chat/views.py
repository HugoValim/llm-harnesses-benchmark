from __future__ import annotations

import os

import httpx
from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render


def chat_index(request: HttpRequest) -> HttpResponse:
    return render(request, "chat/index.html")


def health_check(request: HttpRequest) -> JsonResponse:
    ollama_host = getattr(settings, "OLLAMA_HOST", os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    try:
        resp = httpx.get(f"{ollama_host}/api/tags", timeout=5.0)
        ollama_reachable = resp.status_code == 200
    except Exception:
        ollama_reachable = False

    return JsonResponse(
        {
            "status": "ok" if ollama_reachable else "degraded",
            "ollama_reachable": ollama_reachable,
        }
    )
