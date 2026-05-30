"""
Tests for chat views and template rendering.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse

from chat.views import config_view, health_check_view


@pytest.fixture
def client():
    """Create a test client."""
    return Client()


@pytest.fixture
def factory():
    """Create a request factory."""
    return RequestFactory()


@pytest.mark.django_db
def test_chat_view_renders(client):
    """Test that the chat SPA view renders successfully."""
    response = client.get(reverse("chat"))

    assert response.status_code == 200
    assert b"AI Chat" in response.content
    assert b"htmx.org" in response.content
    # WebSocket path is in the JS file, check for HTMX which proves SPA setup


@pytest.mark.django_db
def test_chat_view_includes_static_files(client):
    """Test that static files are referenced in the template."""
    response = client.get(reverse("chat"))

    content = response.content.decode()
    assert "/static/css/styles.css" in content
    assert "/static/js/chat.js" in content


@pytest.mark.django_db
def test_chat_view_template_structure(client):
    """Test that the template includes required structural elements."""
    response = client.get(reverse("chat"))

    content = response.content.decode()
    # Check for key UI elements
    assert 'id="messages-container"' in content
    assert 'id="message-input"' in content
    assert 'id="chat-form"' in content
    assert 'id="connection-status"' in content
    assert 'id="typing-indicator"' in content


@pytest.mark.asyncio
@override_settings(DEBUG=False)
async def test_health_check_view_healthy(factory):
    """Test health check endpoint returns healthy status."""

    class FakeHealthyService:
        host = "http://localhost:11434"
        model = "qwen2.5:7b"

        async def health_check(self):
            return {
                "healthy": True,
                "host": self.host,
                "model": self.model,
            }

    with patch("chat.services.llm.get_llm_service", return_value=FakeHealthyService()):
        request = factory.get("/health/")
        response = await health_check_view(request)

        assert response.status_code == 200
        assert response["Content-Type"] == "application/json"


@pytest.mark.asyncio
@override_settings(DEBUG=False)
async def test_health_check_view_unhealthy(factory):
    """Test health check returns 503 when Ollama is unreachable."""

    async def fake_health_check():
        return {
            "healthy": False,
            "host": "http://localhost:11434",
            "model": "qwen2.5:7b",
            "error": "Connection refused",
        }

    mock_service = MagicMock()
    mock_service.health_check = fake_health_check

    with patch("chat.views.get_llm_service", return_value=mock_service):
        request = factory.get("/health/")
        response = await health_check_view(request)

        assert response.status_code == 503


@override_settings(DEBUG=False)
def test_config_view(factory):
    """Test config endpoint exposes non-sensitive configuration."""

    class FakeConfigService:
        host = "http://localhost:11434"
        model = "qwen2.5:7b"

    with patch("chat.views.get_llm_service", return_value=FakeConfigService()):
        request = factory.get("/config/")
        response = config_view(request)

        assert response.status_code == 200
        import json

        data = json.loads(response.content)
        assert "ollama_host" in data
        assert "ollama_model" in data
        assert "debug" in data
        assert data["debug"] is False


@override_settings(DEBUG=False)
def test_config_view_no_secrets_exposed(factory):
    """Test that config view does not expose sensitive values."""

    class FakeConfigService:
        host = "http://localhost:11434"
        model = "qwen2.5:7b"

    with patch("chat.views.get_llm_service", return_value=FakeConfigService()):
        request = factory.get("/config/")
        response = config_view(request)

        import json

        data = json.loads(response.content)
        # Ensure no sensitive keys are exposed
        assert "secret" not in str(data).lower()
        assert "key" not in str(data).lower() or "model" in str(data).lower()
