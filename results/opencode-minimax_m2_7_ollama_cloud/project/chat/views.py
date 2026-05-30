import json
import uuid

from django.http import HttpRequest, HttpResponse
from django.template import loader
from django.views.decorators.http import require_http_methods

from .llm_service import get_ollama_service


@require_http_methods(["GET"])
def chat_view(request: HttpRequest) -> HttpResponse:
    template = loader.get_template("chat/index.html")
    session_id = request.session.session_key or str(uuid.uuid4())
    context = {
        "session_id": session_id,
        "ollama_host": "http://localhost:11434",
        "ollama_model": "qwen2.5:7b",
    }
    return HttpResponse(template.render(context, request))


@require_http_methods(["GET"])
def health_view(request: HttpRequest) -> HttpResponse:
    service = get_ollama_service()
    return HttpResponse(
        json.dumps(
            {
                "ollama_host": service._host,
                "ollama_model": service._model,
            }
        ),
        content_type="application/json",
    )
