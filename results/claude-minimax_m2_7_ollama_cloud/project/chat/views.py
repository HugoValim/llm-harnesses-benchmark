"""Views for chat app."""

from django.http import JsonResponse
from django.shortcuts import render

from chat.llm_service import ollama_service


def chat_view(request):
    """Render the chat SPA."""
    return render(request, "chat/index.html")


def health_view(request):
    """Health check endpoint reporting Ollama reachability."""
    status = ollama_service.health_check()
    return JsonResponse(status)
