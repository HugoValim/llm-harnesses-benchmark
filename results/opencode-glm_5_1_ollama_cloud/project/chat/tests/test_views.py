from unittest.mock import AsyncMock, patch

import pytest


class TestIndexView:
    def test_renders_index_template(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert b"Chat" in response.content

    def test_contains_htmx_script(self, client):
        response = client.get("/")
        assert b"htmx.org" in response.content

    def test_contains_ws_extension(self, client):
        response = client.get("/")
        assert b"ext/ws.js" in response.content

    def test_contains_ws_connect(self, client):
        response = client.get("/")
        assert b"ws-connect" in response.content

    def test_contains_ws_send(self, client):
        response = client.get("/")
        assert b"ws-send" in response.content

    def test_static_css_loaded(self, client):
        response = client.get("/")
        assert b"app.css" in response.content


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_endpoint_returns_json(self, async_client):
        with patch("chat.llm.httpx.AsyncClient") as mock_client_cls:
            mock_resp = AsyncMock()
            mock_resp.raise_for_status = lambda: None
            mock_resp.status_code = 200
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            response = await async_client.get("/health/")
            assert response.status_code == 200
