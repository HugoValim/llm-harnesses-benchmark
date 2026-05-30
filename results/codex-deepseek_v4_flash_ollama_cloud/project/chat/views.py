from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from chat.llm_service import check_ollama_health


def chat_view(request: HttpRequest) -> HttpResponse:
    return render(request, "chat/chat.html")


async def health_view(request: HttpRequest) -> JsonResponse:
    status = await check_ollama_health()
    return JsonResponse({"ollama": status})
