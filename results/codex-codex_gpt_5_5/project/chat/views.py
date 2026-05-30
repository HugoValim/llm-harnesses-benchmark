from http import HTTPStatus
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from chat.config import read_ollama_settings


def index(request: HttpRequest) -> HttpResponse:
    """Render the single-page chat UI.

    Example:
        response = index(request)
    """
    return render(request, "chat/index.html", {"websocket_path": "/ws/chat/"})


def ollama_health(_request: HttpRequest) -> JsonResponse:
    """Report Ollama reachability without exposing secret config.

    Example:
        response = ollama_health(request)
    """
    try:
        config = read_ollama_settings()
        status_code = probe_ollama_host(config.host)
    except ImproperlyConfigured as error:
        return JsonResponse(
            {"status": "misconfigured", "detail": str(error)}, status=500
        )
    except (OSError, TimeoutError, URLError) as error:
        return JsonResponse({"status": "unreachable", "detail": str(error)}, status=503)
    return JsonResponse(
        {"status": "reachable", "ollama_status": status_code, "model": config.model},
        status=HTTPStatus.OK,
    )


def probe_ollama_host(host: str) -> int:
    """Return the HTTP status from an Ollama base URL.

    Example:
        status_code = probe_ollama_host("http://localhost:11434")
    """
    request = Request(host, headers={"Accept": "text/plain"}, method="GET")
    with urlopen(request, timeout=2.0) as response:  # nosec B310
        return int(response.status)
