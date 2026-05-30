import pytest
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
def test_index_renders(client: Client) -> None:
    resp = client.get(reverse("index"))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert 'ws-connect="/ws/chat/"' in content
    assert 'ws-send=""' in content
    assert 'htmx-ext="ws"' in content or 'hx-ext="ws"' in content


def test_health_returns_json(client: Client) -> None:
    resp = client.get(reverse("health"))
    assert resp.status_code == 200
    data = resp.json()
    assert "ollama_reachable" in data
