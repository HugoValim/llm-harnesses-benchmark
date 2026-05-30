"""Tests for HTTP views: chat SPA rendering and health check."""

import pytest
from django.test import AsyncClient, Client


@pytest.mark.django_db
class TestChatPage:
    """Chat SPA page renders correctly."""

    def test_renders_status_200(self, client: Client) -> None:
        response = client.get("/")
        assert response.status_code == 200

    def test_contains_htmx_ws_extension(self, client: Client) -> None:
        response = client.get("/")
        content = response.content.decode()
        assert "htmx.org@2.0.4" in content
        assert "ext/ws.js" in content

    def test_contains_ws_connect_attribute(self, client: Client) -> None:
        response = client.get("/")
        content = response.content.decode()
        assert 'ws-connect="/ws/chat/"' in content

    def test_contains_ws_send_attribute(self, client: Client) -> None:
        response = client.get("/")
        content = response.content.decode()
        assert "ws-send" in content

    def test_contains_csrf_token(self, client: Client) -> None:
        response = client.get("/")
        content = response.content.decode()
        assert "csrfmiddlewaretoken" in content


@pytest.mark.django_db
class TestHealthCheck:
    """Health endpoint reports Ollama status."""

    @pytest.fixture
    def async_client(self) -> AsyncClient:
        # Django 6.0 AsyncClient; fallback if needed
        try:
            return AsyncClient()
        except Exception:
            pytest.skip("AsyncClient not available")

    def test_returns_content(self, client: Client) -> None:
        response = client.get("/health/")
        assert response.status_code in (200, 503)
        assert response.content
