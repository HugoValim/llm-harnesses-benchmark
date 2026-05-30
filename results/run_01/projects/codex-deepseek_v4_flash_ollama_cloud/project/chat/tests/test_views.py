import json
from typing import Any
from unittest.mock import AsyncMock

import pytest
from django.http import HttpResponse
from django.test import Client


@pytest.mark.django_db
def test_chat_view_renders() -> None:
    client = Client()
    response: HttpResponse = client.get("/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "ChatLLM" in content
    assert 'hx-ext="ws"' in content
    assert "ws-connect" in content
    assert "ws-send" in content


@pytest.mark.django_db
def test_chat_view_includes_htmx_ws() -> None:
    client = Client()
    response: HttpResponse = client.get("/")
    content = response.content.decode()
    assert "htmx.org" in content
    assert "ws.js" in content


@pytest.mark.django_db
def test_health_view(monkeypatch: Any) -> None:
    import chat.views

    mock = AsyncMock(return_value="ok")
    monkeypatch.setattr(chat.views, "check_ollama_health", mock)

    client = Client()
    response: HttpResponse = client.get("/health/")
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["ollama"] == "ok"
    mock.assert_awaited_once()
