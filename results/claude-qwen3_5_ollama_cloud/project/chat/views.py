"""
Views for the chat application.
"""

import logging

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .services.llm import get_llm_service

logger = logging.getLogger(__name__)


def chat_view(request):
    """
    Main SPA view for the chat application.

    Renders the single-page chat UI with HTMX + WebSocket support.
    """
    return render(request, "chat/chat.html")


@require_http_methods(["GET"])
async def health_check_view(request):
    """
    Health check endpoint for Ollama connectivity.

    Returns JSON with Ollama status - no secrets exposed.
    """
    llm_service = get_llm_service()
    result = await llm_service.health_check()
    status_code = 200 if result["healthy"] else 503
    return JsonResponse(result, status=status_code)


@require_http_methods(["GET"])
def config_view(request):
    """
    Expose non-sensitive configuration to the frontend.

    Returns the Ollama host/model for client-side display.
    Does NOT expose SECRET_KEY or other sensitive values.
    """
    return JsonResponse(
        {
            "ollama_host": get_llm_service().host,
            "ollama_model": get_llm_service().model,
            "debug": False,  # Never expose debug status in production
        }
    )
