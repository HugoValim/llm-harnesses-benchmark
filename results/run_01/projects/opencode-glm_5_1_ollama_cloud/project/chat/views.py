from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from chat.llm import check_ollama_health


def index(request: HttpRequest) -> HttpResponse:
    return render(request, "chat/index.html")


async def health_check(request: HttpRequest) -> JsonResponse:
    status = await check_ollama_health()
    return JsonResponse(status)
