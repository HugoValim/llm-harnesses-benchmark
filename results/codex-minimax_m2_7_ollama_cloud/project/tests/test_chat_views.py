"""Tests for chat views and template rendering."""

import pytest


@pytest.mark.django_db
class TestChatViews:
    """View-level tests for the chat application."""

    def test_home_view_renders(self, client):
        """Home view returns 200 and uses correct template."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response["Content-Type"]

    def test_home_template_includes_htmx_ws(self, client):
        """Template includes HTMX WebSocket extension scripts."""
        response = client.get("/")
        content = response.content.decode()
        assert "htmx.min.js" in content
        assert "ws.js" in content
        assert 'hx-ext="ws"' in content

    def test_home_template_wires_websocket_route(self, client):
        """Template connects to the WebSocket route and uses ws-send."""
        response = client.get("/")
        content = response.content.decode()
        assert 'ws-connect="/ws/chat/"' in content
        assert "ws-send" in content

    def test_home_template_includes_tailwind_css(self, client):
        """Template loads Tailwind-built CSS."""
        response = client.get("/")
        content = response.content.decode()
        assert "css/styles.css" in content

    def test_health_check_returns_json(self, client):
        """Health check returns JSON with status."""
        response = client.get("/health/")
        assert response.status_code in (200, 503, 500)
        assert "application/json" in response["Content-Type"]
        data = response.json()
        assert "ollama" in data
        assert "host" in data
        assert "model" in data

    def test_health_check_does_not_leak_secrets(self, client):
        """Health check never exposes secret key or tokens."""
        response = client.get("/health/")
        content = response.content.decode()
        secret_words = ("SECRET", "KEY", "token", "password", "Bearer")
        for word in secret_words:
            assert word not in content or word.lower() in ("model", "host", "ollama"), (
                f"Health check leaked: {word}"
            )

    def test_home_view_context_has_no_secrets(self, client):
        """Home view context does not leak secrets."""
        response = client.get("/")
        content = response.content.decode()
        assert "django-insecure" not in content.lower()
        assert "test-secret" not in content.lower()
