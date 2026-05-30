import logging

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from .services import check_ollama_reachability

logger = logging.getLogger(__name__)


def chat_page(request: HttpRequest) -> HttpResponse:
    return render(request, "chat/chat.html")


async def health_check(request: HttpRequest) -> JsonResponse:
    reachable = await check_ollama_reachability()
    return JsonResponse(
        {
            "ollama_host": settings.OLLAMA_HOST,
            "ollama_model": settings.OLLAMA_MODEL,
            "ollama_reachable": reachable,
        }
    )
