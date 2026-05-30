"""Views for the chat SPA."""

from __future__ import annotations

import httpx
from django.http import HttpRequest, HttpResponse
from django.views import View

from chat.services.llm import _ollama_host


class IndexView(View):
    """Render the single-page chat application."""

    def get(self, request: HttpRequest) -> HttpResponse:
        from django.template.loader import render_to_string

        html = render_to_string("chat/index.html", request=request)
        return HttpResponse(html)


class HealthView(View):
    """Lightweight health-check endpoint — reports Ollama reachability."""

    def get(self, request: HttpRequest) -> HttpResponse:
        host = _ollama_host()
        try:
            resp = httpx.get(f"{host}/api/tags", timeout=3.0)
            reachable = resp.status_code == 200
        except Exception:
            reachable = False

        status = 200 if reachable else 503
        return HttpResponse(
            f'{{"ollama_reachable": {reachable}, "host": "{host}"}}',
            content_type="application/json",
            status=status,
        )
