"""
Tests for chatapp views and templates.
"""

from typing import AsyncGenerator

import pytest
from django.template.loader import render_to_string
from django.test import Client
from django.urls import reverse


class FakeChunk:
    """Fake response chunk."""

    def __init__(self, content: str) -> None:
        self.content = content


class FakeChatModel:
    """Fake ChatOllama for testing streaming behavior."""

    def __init__(self, chunks: list[str] | None = None) -> None:
        self.chunks = chunks or ["Hello", " ", "world", "!"]

    async def astream(
        self, messages: list[dict[str, str]]
    ) -> AsyncGenerator[FakeChunk, None]:
        """Stream fake chunks."""
        for chunk_text in self.chunks:
            yield FakeChunk(chunk_text)


@pytest.mark.django_db
class TestChatView:
    """Test chat view rendering."""

    def test_chat_view_renders(self, client: Client) -> None:
        """Test that chat view renders successfully."""
        response = client.get(reverse("chat"))
        assert response.status_code == 200
        assert b"Chat - Ollama Stream" in response.content

    def test_chat_view_contains_htmx_ws_extension(self, client: Client) -> None:
        """Test that chat template loads HTMX WebSocket extension."""
        response = client.get(reverse("chat"))
        content = response.content.decode()
        assert "htmx.org/dist/ext/ws.js" in content
        assert "ws-connect" in content
        assert "ws-send" in content

    def test_chat_template_renders(self) -> None:
        """Test template rendering with context."""
        html = render_to_string("chat.html")
        assert 'ws-connect="/ws/chat/"' in html
        assert "htmx.org/dist/ext/ws.js" in html


@pytest.mark.django_db
class TestHealthView:
    """Test health check views."""

    def test_health_view_renders(self, client: Client) -> None:
        """Test health view renders."""
        response = client.get(reverse("health"))
        assert response.status_code == 200
        assert b"Ollama Health Check" in response.content

    def test_api_health_endpoint(self, client: Client) -> None:
        """Test API health endpoint returns JSON."""
        response = client.get(reverse("api_health"))
        assert response.status_code in (200, 503)
        assert "ollama_reachable" in response.json()
