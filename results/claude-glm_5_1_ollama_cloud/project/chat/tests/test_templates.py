from __future__ import annotations

import pytest
from django.template.loader import get_template


@pytest.mark.django_db
def test_index_template_renders():
    template = get_template("chat/index.html")
    rendered = template.render()
    assert "ws-connect" in rendered
    assert "chat-form" in rendered
    assert "messages" in rendered


@pytest.mark.django_db
def test_input_template_renders():
    template = get_template("chat/input.html")
    rendered = template.render()
    assert "chat-input" in rendered
    assert "ws-send" in rendered
    assert "Send" in rendered


@pytest.mark.django_db
def test_message_list_template_renders():
    template = get_template("chat/message_list.html")
    rendered = template.render()
    assert isinstance(rendered, str)


@pytest.mark.django_db
def test_error_partial_template_renders():
    template = get_template("chat/_error.html")
    rendered = template.render({"error_message": "Test error"})
    assert "Test error" in rendered
    assert "bg-red-900" in rendered
