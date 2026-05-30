"""
Views for chat application.
"""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


async def chat_view(request: HttpRequest) -> HttpResponse:
    """Render the main chat page."""
    return render(request, "chat/chat.html")


async def health_check_view(request: HttpRequest) -> HttpResponse:
    """Health check endpoint."""
    from .llm_service import LLMService

    service = LLMService()
    is_healthy = await service.health_check()

    return HttpResponse(
        "OK" if is_healthy else "Service Unavailable",
        status=200 if is_healthy else 503,
    )
