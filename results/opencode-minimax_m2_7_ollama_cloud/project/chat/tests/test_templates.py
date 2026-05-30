import pytest
from django.test import Client


@pytest.mark.django_db
def test_index_template_contains_htmx_ws_extension() -> None:
    client = Client()
    response = client.get("/chat/")

    content = response.content.decode()
    assert "htmx" in content.lower()
    assert 'hx-ext="ws"' in content or "ws-connect" in content


@pytest.mark.django_db
def test_index_template_has_message_list_partial() -> None:
    client = Client()
    response = client.get("/chat/")

    content = response.content.decode()
    assert "message-list" in content or "chat-messages" in content


@pytest.mark.django_db
def test_index_template_has_input_form() -> None:
    client = Client()
    response = client.get("/chat/")

    content = response.content.decode()
    assert "message-input" in content
    assert "send-button" in content or 'type="submit"' in content


@pytest.mark.django_db
def test_index_template_includes_static_css() -> None:
    client = Client()
    response = client.get("/chat/")

    content = response.content.decode()
    assert "styles.css" in content


@pytest.mark.django_db
def test_index_template_includes_htmx_js() -> None:
    client = Client()
    response = client.get("/chat/")

    content = response.content.decode()
    assert "htmx.min.js" in content


@pytest.mark.django_db
def test_index_template_includes_ws_js() -> None:
    client = Client()
    response = client.get("/chat/")

    content = response.content.decode()
    assert "ws.js" in content
