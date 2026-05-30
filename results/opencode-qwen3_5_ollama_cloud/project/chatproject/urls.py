"""
URL configuration for chatproject project.
"""

import os

import httpx
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path

from chatapp.llm_service import get_chat_model
from chatapp.views import chat_view, health_check


def api_health(request):
    """API health check endpoint for Ollama reachability."""
    try:
        get_chat_model()
        ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        ollama_model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")

        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{ollama_host}/api/tags")
            if response.status_code == 200:
                return JsonResponse(
                    {
                        "ollama_reachable": True,
                        "model": ollama_model,
                        "host": ollama_host,
                    }
                )
    except Exception as e:
        return JsonResponse(
            {
                "ollama_reachable": False,
                "error": str(e),
            },
            status=503,
        )

    return JsonResponse(
        {
            "ollama_reachable": False,
            "error": "Unknown error",
        },
        status=503,
    )


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", chat_view, name="chat"),
    path("health/", health_check, name="health"),
    path("api/health/", api_health, name="api_health"),
]
