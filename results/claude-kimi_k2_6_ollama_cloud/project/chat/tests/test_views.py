import pytest
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
def test_index_renders_spa():
    client = Client()
    response = client.get(reverse("index"))
    assert response.status_code == 200
    content = response.content.decode()
    assert 'hx-ext="ws"' in content
    assert 'ws-connect="/ws/chat/"' in content
    assert "ws-send" in content
    assert 'id="chat-form"' in content
    assert 'id="message-input"' in content
    assert "htmx-ext-ws" in content or "ws.js" in content


@pytest.mark.django_db
def test_health_returns_json(client):
    response = client.get(reverse("health"))
    assert response.status_code == 200
    data = response.json()
    assert "ollama_reachable" in data
    assert "model" in data
