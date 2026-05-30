from __future__ import annotations

import pytest
from django.template.loader import render_to_string


@pytest.mark.django_db
def test_spa_template_renders_expected_fragments() -> None:
    html = render_to_string("chat/spa.html", {})
    assert "ws-connect=" in html
    assert 'id="thread"' in html
    assert 'name="message"' in html


@pytest.mark.django_db
def test_partials_render_independently() -> None:
    header = render_to_string("chat/partials/header.html", {})
    assert "HTMX WebSocket extension" in header

    composer = render_to_string("chat/partials/composer.html", {})
    assert 'name="message"' in composer
