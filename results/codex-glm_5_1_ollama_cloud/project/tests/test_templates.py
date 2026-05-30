"""Template rendering tests — verify HTMX WebSocket extension wiring."""

from __future__ import annotations

from django.template.loader import render_to_string


class TestIndexTemplate:
    def test_renders_without_error(self) -> None:
        html = render_to_string("chat/index.html")
        assert html

    def test_htmx_ws_extension_attribute(self) -> None:
        html = render_to_string("chat/index.html")
        assert 'hx-ext="ws"' in html

    def test_ws_connect_attribute(self) -> None:
        html = render_to_string("chat/index.html")
        assert "ws-connect" in html

    def test_ws_send_attribute(self) -> None:
        html = render_to_string("chat/index.html")
        assert "ws-send" in html

    def test_htmx_script_tag(self) -> None:
        html = render_to_string("chat/index.html")
        assert "htmx.min.js" in html

    def test_htmx_ws_extension_script(self) -> None:
        html = render_to_string("chat/index.html")
        assert "htmx-ws.js" in html

    def test_tailwind_css_linked(self) -> None:
        html = render_to_string("chat/index.html")
        assert "dist/styles.css" in html

    def test_chat_form_present(self) -> None:
        html = render_to_string("chat/index.html")
        assert 'id="chat-form"' in html

    def test_messages_container(self) -> None:
        html = render_to_string("chat/index.html")
        assert 'id="messages"' in html

    def test_error_banner(self) -> None:
        html = render_to_string("chat/index.html")
        assert 'id="error-banner"' in html
