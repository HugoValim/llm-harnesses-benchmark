from django.template.loader import render_to_string


class TestTemplates:
    def test_index_renders(self):
        html = render_to_string("chat/index.html")
        assert "Chat" in html
        assert "htmx" in html
        assert "ws-connect" in html

    def test_input_partial_renders(self):
        html = render_to_string("chat/_input.html")
        assert "ws-send" in html
        assert 'name="message"' in html

    def test_message_partial_renders(self):
        html = render_to_string(
            "chat/_message.html",
            {
                "role_class": "justify-end",
                "bubble_class": "bg-blue-600",
                "content": "test",
            },
        )
        assert "test" in html

    def test_index_has_css_link(self):
        html = render_to_string("chat/index.html")
        assert "app.css" in html

    def test_index_has_ws_extension(self):
        html = render_to_string("chat/index.html")
        assert "ext/ws.js" in html
        assert "hx-ext" in html
