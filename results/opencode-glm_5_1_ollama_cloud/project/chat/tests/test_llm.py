from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat.llm import check_ollama_health, get_chat_model, stream_response


class TestGetChatModel:
    @patch("chat.llm.ChatOllama")
    def test_creates_model_with_settings(self, mock_ollama):
        with patch("chat.llm.settings") as mock_settings:
            mock_settings.OLLAMA_MODEL = "test-model"
            mock_settings.OLLAMA_HOST = "http://test:11434"
            get_chat_model()
            mock_ollama.assert_called_once_with(
                model="test-model",
                base_url="http://test:11434",
            )


class TestStreamResponse:
    @pytest.mark.asyncio
    async def test_yields_tokens_from_model(self):
        from langchain_core.messages import AIMessageChunk

        chunks = [
            AIMessageChunk(content="Hello"),
            AIMessageChunk(content=" world"),
            AIMessageChunk(content="!"),
        ]

        async def fake_astream(messages):
            for chunk in chunks:
                yield chunk

        mock_model = MagicMock()
        mock_model.astream = fake_astream

        with patch("chat.llm.get_chat_model", return_value=mock_model):
            results = []
            async for token in stream_response([{"role": "user", "content": "hi"}]):
                results.append(token)

            assert results == ["Hello", " world", "!"]

    @pytest.mark.asyncio
    async def test_skips_empty_content(self):
        from langchain_core.messages import AIMessageChunk

        chunks = [
            AIMessageChunk(content="Hi"),
            AIMessageChunk(content=""),
            AIMessageChunk(content="!"),
        ]

        async def fake_astream(messages):
            for chunk in chunks:
                yield chunk

        mock_model = MagicMock()
        mock_model.astream = fake_astream

        with patch("chat.llm.get_chat_model", return_value=mock_model):
            results = []
            async for token in stream_response([{"role": "user", "content": "hi"}]):
                results.append(token)

            assert results == ["Hi", "!"]

    @pytest.mark.asyncio
    async def test_builds_messages_with_system_and_human(self):
        received_messages = None

        async def fake_astream(messages):
            nonlocal received_messages
            received_messages = messages
            yield AIMessageChunk(content="ok")

        from langchain_core.messages import AIMessageChunk

        mock_model = MagicMock()
        mock_model.astream = fake_astream

        with patch("chat.llm.get_chat_model", return_value=mock_model):
            async for _ in stream_response(
                [
                    {"role": "system", "content": "You are helpful"},
                    {"role": "user", "content": "hello"},
                ]
            ):
                pass

        from langchain_core.messages import HumanMessage, SystemMessage

        assert any(isinstance(m, SystemMessage) for m in received_messages)
        assert any(isinstance(m, HumanMessage) for m in received_messages)


class TestCheckOllamaHealth:
    @pytest.mark.asyncio
    async def test_reachable(self):
        with patch("chat.llm.settings") as mock_settings:
            mock_settings.OLLAMA_HOST = "http://localhost:11434"
            with patch("chat.llm.httpx.AsyncClient") as mock_client_cls:
                mock_resp = AsyncMock()
                mock_resp.raise_for_status = MagicMock()
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_resp)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client_cls.return_value = mock_client

                result = await check_ollama_health()
                assert result["reachable"] is True

    @pytest.mark.asyncio
    async def test_unreachable(self):
        with patch("chat.llm.settings") as mock_settings:
            mock_settings.OLLAMA_HOST = "http://localhost:11434"
            with patch("chat.llm.httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(side_effect=Exception("connection refused"))
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client_cls.return_value = mock_client

                result = await check_ollama_health()
                assert result["reachable"] is False
                assert "connection refused" in result["error"]
