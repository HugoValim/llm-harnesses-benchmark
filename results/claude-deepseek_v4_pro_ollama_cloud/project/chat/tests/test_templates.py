import pytest
from django.template.loader import render_to_string


@pytest.mark.django_db
def test_index_template_renders() -> None:
    html = render_to_string("chat/index.html", {"debug": True})
    assert "<!DOCTYPE html>" in html
    assert "chat-messages" in html
    assert "ws-connect" in html


@pytest.mark.django_db
def test_message_partial_user() -> None:
    html = render_to_string(
        "chat/partials/message.html",
        {"role": "user", "content": "Hello"},
    )
    assert "Hello" in html
    assert "justify-end" in html


@pytest.mark.django_db
def test_message_partial_assistant() -> None:
    html = render_to_string(
        "chat/partials/message.html",
        {"role": "assistant", "content": "Hi there"},
    )
    assert "Hi there" in html
    assert "justify-start" in html
