from __future__ import annotations

import pytest
from django.test import Client, RequestFactory

from chat.views import chat_index


@pytest.mark.django_db
def test_chat_index_returns_200():
    factory = RequestFactory()
    request = factory.get("/")
    response = chat_index(request)
    assert response.status_code == 200


@pytest.mark.django_db
def test_chat_index_uses_correct_template():
    client = Client()
    response = client.get("/")
    assert "chat/index.html" in [t.name for t in response.templates]


@pytest.mark.django_db
def test_chat_index_contains_csrf():
    client = Client()
    response = client.get("/")
    content = response.content.decode()
    assert "csrfmiddlewaretoken" in content.lower() or "csrf" in content.lower()


@pytest.mark.django_db
def test_chat_index_contains_htmx_ws():
    client = Client()
    response = client.get("/")
    content = response.content.decode()
    assert "htmx.min.js" in content
    assert "htmx-ws.js" in content
    assert "ws-connect" in content
    assert "ws-send" in content
    assert "/ws/chat/" in content
