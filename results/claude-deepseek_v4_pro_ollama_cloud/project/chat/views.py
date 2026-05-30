from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render


def index(request: HttpRequest) -> HttpResponse:
    return render(request, "chat/index.html", {"debug": settings.DEBUG})


async def health(request: HttpRequest) -> JsonResponse:
    from .llm_service import LLMService

    svc = LLMService()
    result = await svc.check_health()
    return JsonResponse(result)
