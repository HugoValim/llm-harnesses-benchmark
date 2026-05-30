import logging

from django.http import JsonResponse
from django.shortcuts import render

from chat.llm_service import check_ollama_reachable

logger = logging.getLogger(__name__)


def chat_view(request):
    return render(request, 'chat/chat.html')


def health_check(request):
    ollama_ok = check_ollama_reachable()
    status = 200 if ollama_ok else 503
    return JsonResponse(
        {'ollama_reachable': ollama_ok, 'status': 'ok' if ollama_ok else 'unhealthy'},
        status=status,
    )
