"""Tests for chat views — index and health endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.test import Client


@pytest.fixture()
def client() -> Client:
    return Client()


class TestIndexView:
    def test_returns_200(self, client: Client) -> None:
        resp = client.get("/")
        assert resp.status_code == 200

    def test_contains_htmx_ws_ext(self, client: Client) -> None:
        resp = client.get("/")
        content = resp.content.decode()
        assert 'hx-ext="ws"' in content

    def test_contains_ws_connect(self, client: Client) -> None:
        resp = client.get("/")
        content = resp.content.decode()
        assert "ws-connect" in content

    def test_contains_ws_send(self, client: Client) -> None:
        resp = client.get("/")
        content = resp.content.decode()
        assert "ws-send" in content

    def test_renders_chat_area(self, client: Client) -> None:
        resp = client.get("/")
        content = resp.content.decode()
        assert 'id="messages"' in content

    def test_includes_htmx_script(self, client: Client) -> None:
        resp = client.get("/")
        content = resp.content.decode()
        assert "htmx.min.js" in content

    def test_includes_ws_extension_script(self, client: Client) -> None:
        resp = client.get("/")
        content = resp.content.decode()
        assert "htmx-ws.js" in content


class TestHealthView:
    @patch("chat.views.httpx")
    def test_health_ollama_reachable(self, mock_httpx: MagicMock, client: Client) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_httpx.get.return_value = mock_response

        resp = client.get("/health/")
        assert resp.status_code == 200
        assert b"ollama_reachable" in resp.content

    @patch("chat.views.httpx")
    def test_health_ollama_unreachable(self, mock_httpx: MagicMock, client: Client) -> None:
        mock_httpx.get.side_effect = Exception("connection refused")

        resp = client.get("/health/")
        assert resp.status_code == 503
