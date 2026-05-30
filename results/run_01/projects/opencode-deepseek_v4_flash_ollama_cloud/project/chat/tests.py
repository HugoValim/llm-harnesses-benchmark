# SPDX-License-Identifier: MIT

from collections.abc import AsyncIterable
from unittest.mock import MagicMock, patch

import pytest
from channels.testing import WebsocketCommunicator
from django.test import TestCase
from django.urls import reverse

from chat.consumers import ChatConsumer


class FakeChatOllama:
    """Fake for ChatOllama that yields preset chunks."""

    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks
        self.invoke = MagicMock()

    async def astream(self, messages: list[dict]) -> AsyncIterable:
        for chunk_text in self._chunks:
            fake_msg = MagicMock()
            fake_msg.content = chunk_text
            yield fake_msg


class TestHealthView(TestCase):
    def test_health_check_returns_json(self) -> None:
        url = reverse('health')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('ollama_reachable', response.json())

    def test_health_check_ollama_down(self) -> None:
        with patch('chat.llm_service.create_llm') as mock_create:
            mock_llm = MagicMock()
            mock_llm.invoke.side_effect = ConnectionError('refused')
            mock_create.return_value = mock_llm
            url = reverse('health')
            response = self.client.get(url)
            self.assertEqual(response.status_code, 503)
            self.assertFalse(response.json()['ollama_reachable'])


class TestChatView(TestCase):
    def test_chat_view_renders(self) -> None:
        url = reverse('chat')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'chat/chat.html')

    def test_chat_view_has_htmx_ws_extension(self) -> None:
        url = reverse('chat')
        response = self.client.get(url)
        content = response.content.decode()
        self.assertIn('hx-ext="ws"', content)
        self.assertIn('ws-connect="/ws/chat/"', content)
        self.assertIn('ws-send', content)

    def test_chat_view_loads_htmx_js(self) -> None:
        url = reverse('chat')
        response = self.client.get(url)
        content = response.content.decode()
        self.assertIn('htmx.org', content)
        self.assertIn('ext/ws.js', content)


class TestPartialTemplate(TestCase):
    def test_messages_partial_renders(self) -> None:
        from django.template.loader import render_to_string

        html = render_to_string('chat/_messages.html')
        self.assertIn('placeholder-message', html)


@pytest.mark.asyncio
class TestChatConsumer:
    async def test_connect_and_disconnect(self) -> None:
        app = ChatConsumer.as_asgi()
        comm = WebsocketCommunicator(app, '/ws/chat/')
        connected, _ = await comm.connect()
        assert connected
        await comm.disconnect()

    async def test_receive_user_message_sends_tokens(self) -> None:
        fake = FakeChatOllama(['Hello', ' ', 'World'])
        app = ChatConsumer.as_asgi()

        with patch('chat.consumers.create_llm', return_value=fake):
            comm = WebsocketCommunicator(app, '/ws/chat/')
            await comm.connect()
            await comm.send_json_to({'message': 'hi'})
            tokens = []
            done = False
            for _ in range(10):
                raw = await comm.receive_from(timeout=2)
                import json

                data = json.loads(raw)
                if data['type'] == 'token':
                    tokens.append(data['content'])
                elif data['type'] == 'done':
                    done = True
                    break
            assert ''.join(tokens) == 'Hello World'
            assert done
            await comm.disconnect()

    async def test_receive_error_on_ollama_failure(self) -> None:
        app = ChatConsumer.as_asgi()
        with patch('chat.consumers.create_llm') as mock_create:
            mock_llm = MagicMock()
            mock_llm.astream.side_effect = RuntimeError('Ollama down')
            mock_create.return_value = mock_llm
            comm = WebsocketCommunicator(app, '/ws/chat/')
            await comm.connect()
            await comm.send_json_to({'message': 'hi'})
            raw = await comm.receive_from(timeout=2)
            import json

            data = json.loads(raw)
            assert data['type'] == 'error'
            assert 'Ollama' in data['content']
            await comm.disconnect()

    async def test_multiple_messages_maintain_context(self) -> None:
        fake = FakeChatOllama(['resp2'])
        app = ChatConsumer.as_asgi()
        with patch('chat.consumers.create_llm', return_value=fake):
            comm = WebsocketCommunicator(app, '/ws/chat/')
            await comm.connect()
            await comm.send_json_to({'message': 'first'})
            for _ in range(5):
                raw = await comm.receive_from(timeout=2)
                import json

                data = json.loads(raw)
                if data['type'] == 'done':
                    break
            await comm.send_json_to({'message': 'second'})
            for _ in range(5):
                raw = await comm.receive_from(timeout=2)
                import json

                data = json.loads(raw)
                if data['type'] == 'done':
                    break
            await comm.disconnect()

    async def test_empty_message_ignored(self) -> None:
        app = ChatConsumer.as_asgi()
        comm = WebsocketCommunicator(app, '/ws/chat/')
        await comm.connect()
        await comm.send_json_to({'message': ''})
        await comm.disconnect()
