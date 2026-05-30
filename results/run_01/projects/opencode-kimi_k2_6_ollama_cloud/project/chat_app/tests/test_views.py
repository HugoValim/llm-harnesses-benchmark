import pytest
from django.test import Client


@pytest.fixture
def client() -> Client:
    return Client()


@pytest.mark.django_db
def test_chat_page_renders(client: Client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    content = response.content.decode()
    assert 'hx-ext="ws"' in content
    assert 'ws-connect="/ws/chat/"' in content
    assert "ws-send" in content


@pytest.mark.django_db
def test_chat_page_has_htmx_ws_script(client: Client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "htmx-ext-ws" in content or "ws.js" in content or 'hx-ext="ws"' in content


@pytest.mark.django_db
def test_health_returns_json(client: Client) -> None:
    response = client.get("/health/")
    assert response.status_code == 200
    data = response.json()
    assert "ollama_reachable" in data
    assert "model" in data
