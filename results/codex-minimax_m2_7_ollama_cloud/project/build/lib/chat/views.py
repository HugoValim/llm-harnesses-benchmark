"""Chat views."""

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from chat.services.llm import ChatService, OllamaConnectionError


def home(request: HttpRequest) -> HttpResponse:
    """Render the chat SPA."""
    return render(request, "chat/home.html")


@require_http_methods(["GET"])
def health_check(request: HttpRequest) -> JsonResponse:
    """Report Ollama reachability without exposing secrets."""
    host = settings.OLLAMA_HOST
    model = settings.OLLAMA_MODEL
    try:
        service = ChatService()
        for _ in service.client.stream(["ping"]):
            pass
        return JsonResponse(
            {
                "ollama": "reachable",
                "host": host,
                "model": model,
            }
        )
    except OllamaConnectionError:
        return JsonResponse(
            {
                "ollama": "unreachable",
                "host": host,
                "model": model,
            },
            status=503,
        )
    except Exception:
        return JsonResponse(
            {
                "ollama": "unknown",
                "host": host,
                "model": model,
            },
            status=500,
        )
