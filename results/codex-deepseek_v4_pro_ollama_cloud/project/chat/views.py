"""HTTP views: chat SPA page and health check."""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from chat.services import check_ollama_health


async def chat_page(request: HttpRequest) -> HttpResponse:
    """Serve the single-page chat UI."""
    return render(request, "chat/chat.html")


async def health_check(request: HttpRequest) -> HttpResponse:
    """Report Ollama reachability without exposing secrets."""
    status = await check_ollama_health()
    if status["reachable"]:
        return HttpResponse(
            f'OK — model "{status["model"]}" reachable',
            content_type="text/plain",
        )
    return HttpResponse(
        f"UNAVAILABLE: {status.get('error', 'unknown')}",
        content_type="text/plain",
        status=503,
    )
