"""HTTP view and template-rendering tests for the chat SPA.

These prove the single page renders with its partials, that the HTMX WebSocket
extension is wired to the consumer route, and that the health endpoint reports
Ollama reachability through the (faked) service boundary.
"""

from __future__ import annotations

import pytest
from django.template.loader import render_to_string
from django.test import Client
from django.urls import reverse

from chat import views
from chat.routing import websocket_urlpatterns
from tests.fakes import FakeChatService


@pytest.fixture
def client() -> Client:
    return Client()


def test_index_renders_spa_shell(client: Client) -> None:
    response = client.get(reverse("chat:index"))
    assert response.status_code == 200
    body = response.content.decode()
    assert "<title>Ollama Chat</title>" in body
    # Partials are included, not duplicated inline.
    assert "Streaming via LangChain + Django Channels" in body  # header partial
    assert "stream the answer token by token" in body  # welcome partial


def test_index_wires_htmx_websocket_extension(client: Client) -> None:
    body = client.get(reverse("chat:index")).content.decode()
    assert 'hx-ext="ws"' in body
    assert 'ws-connect="/ws/chat/"' in body
    assert "ws-send" in body
    # The HTMX core and ws extension scripts are loaded (no raw `new WebSocket`).
    assert "js/htmx.min.js" in body
    assert "js/ws.js" in body
    assert "new WebSocket" not in body


def test_ws_connect_path_matches_routing(client: Client) -> None:
    body = client.get(reverse("chat:index")).content.decode()
    routed = {str(p.pattern) for p in websocket_urlpatterns}
    assert "ws/chat/" in routed
    assert 'ws-connect="/ws/chat/"' in body


def test_health_reports_reachable(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        views, "create_chat_service", lambda: FakeChatService(healthy=True, model="qwen2.5:7b")
    )
    response = client.get(reverse("chat:health"))
    assert response.status_code == 200
    payload = response.json()
    assert payload == {"status": "ok", "ollama_reachable": True, "model": "qwen2.5:7b"}


def test_health_reports_degraded_when_unreachable(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(views, "create_chat_service", lambda: FakeChatService(healthy=False))
    response = client.get(reverse("chat:health"))
    assert response.status_code == 503
    assert response.json()["ollama_reachable"] is False


def test_token_partial_renders_oob_swap() -> None:
    html = render_to_string("chat/partials/token.html", {"turn_id": 7, "token": "Hi"})
    assert 'hx-swap-oob="beforeend:#assistant-content-7"' in html
    assert ">Hi<" in html


def test_error_partial_includes_detail() -> None:
    html = render_to_string("chat/partials/error.html", {"turn_id": 1, "detail": "boom"})
    assert "boom" in html
    assert "unavailable" in html.lower()
