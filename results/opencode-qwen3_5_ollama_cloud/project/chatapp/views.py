"""
Chat app views.
"""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def chat_view(request: HttpRequest) -> HttpResponse:
    """Render the main chat SPA."""
    return render(request, "chat.html")


def health_check(request: HttpRequest) -> HttpResponse:
    """Health check endpoint for Ollama reachability."""
    return render(request, "health.html")
