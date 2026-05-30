"""HTTP view and template tests."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from django.test import Client


@pytest.mark.django_db
def test_chat_index_renders_spa(client: Client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    html = response.content.decode()
    assert 'hx-ext="ws"' in html
    assert 'ws-connect="/ws/chat/"' in html
    assert "ws-send" in html
    assert "/dist/ext/ws.js" in html or "ext/ws.js" in html
    assert 'id="messages"' in html


@pytest.mark.django_db
def test_chat_index_includes_partials_structure(client: Client) -> None:
    response = client.get("/")
    html = response.content.decode()
    assert "Ollama Chat" in html
    assert 'name="message"' in html


@pytest.mark.django_db
def test_ollama_health_reports_reachable(client: Client) -> None:
    with patch("chat.services.llm.check_ollama_reachable", return_value=(True, "ok")):
        response = client.get("/health/ollama/")
    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload["reachable"] is True
    assert payload["configured_model"]


@pytest.mark.django_db
def test_ollama_health_reports_unreachable(client: Client) -> None:
    with patch(
        "chat.services.llm.check_ollama_reachable",
        return_value=(False, "Ollama unreachable"),
    ):
        response = client.get("/health/ollama/")
    assert response.status_code == 503
    payload = json.loads(response.content)
    assert payload["reachable"] is False
