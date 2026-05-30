"""
Tests for chat views.
"""

import pytest
from django.test import AsyncClient


@pytest.mark.asyncio
async def test_chat_view_renders() -> None:
    """Test that chat view renders the SPA."""
    client = AsyncClient()
    response = await client.get("/")

    assert response.status_code == 200
    assert b"Chat" in response.content
    assert b"htmx.org" in response.content
    assert b"ws-connect" in response.content


@pytest.mark.asyncio
async def test_chat_view_has_tailwind_css() -> None:
    """Test that chat view includes Tailwind CSS."""
    client = AsyncClient()
    response = await client.get("/")

    assert response.status_code == 200
    assert b"styles.css" in response.content


@pytest.mark.asyncio
async def test_chat_view_has_htmx_ws_extension() -> None:
    """Test that chat view loads HTMX WebSocket extension."""
    client = AsyncClient()
    response = await client.get("/")

    assert response.status_code == 200
    assert b"htmx.org/dist/ext/ws.js" in response.content


@pytest.mark.asyncio
async def test_health_check_view_success() -> None:
    """Test health check endpoint."""
    client = AsyncClient()
    response = await client.get("/health/")

    assert response.status_code in (200, 503)
