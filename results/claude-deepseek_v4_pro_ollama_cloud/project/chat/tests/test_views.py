import pytest
from django.test import Client


@pytest.mark.django_db
def test_index_returns_200() -> None:
    client = Client()
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response["Content-Type"]


@pytest.mark.django_db
def test_index_contains_chat_ui() -> None:
    client = Client()
    response = client.get("/")
    content = response.content.decode()
    assert "chat-messages" in content
    assert "message-input" in content
    assert "send-button" in content
    assert "/ws/chat/" in content


@pytest.mark.django_db
def test_index_contains_htmx() -> None:
    client = Client()
    response = client.get("/")
    content = response.content.decode()
    assert "htmx.org" in content
    assert "htmx-ext-ws" in content


@pytest.mark.django_db
def test_health_returns_json() -> None:
    client = Client()
    response = client.get("/health/")
    assert response.status_code == 200
    data = response.json()
    assert "reachable" in data
    assert "model" in data
