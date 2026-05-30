from __future__ import annotations

from unittest.mock import patch

import pytest
from channels.testing import WebsocketCommunicator
from chat_project.asgi import application
from django.test import Client

from chat.tests.fakes import FakeChatOllamaClient


@pytest.mark.asyncio
@patch("chat.llm_service.build_chat_ollama", return_value=FakeChatOllamaClient(["x", "y", "z"]))
async def test_chat_consumer_streams_multiple_ws_messages(_mock: object) -> None:
    communicator = WebsocketCommunicator(
        application,
        "/ws/chat/",
        headers=[(b"origin", b"http://127.0.0.1")],
    )
    connected, _ = await communicator.connect()
    assert connected is True

    await communicator.send_to(text_data='{"message":"hello"}')

    frames: list[str] = []
    for _ in range(50):
        msg = await communicator.receive_from()
        frames.append(msg)
        if len([f for f in frames if ">z<" in f or ">y<" in f or ">x<" in f]) >= 3:
            break

    await communicator.disconnect()

    assert any(">x<" in f for f in frames)
    assert any(">y<" in f for f in frames)
    assert any(">z<" in f for f in frames)


@pytest.mark.django_db
def test_chat_spa_renders_partials_and_ws_connect() -> None:
    client = Client()
    response = client.get("/")
    assert response.status_code == 200
    body = response.content.decode()
    assert 'ws-connect="/ws/chat/"' in body
    assert 'name="message"' in body
    assert "Ollama Chat" in body


@pytest.mark.django_db
def test_health_endpoint_reports_shape() -> None:
    client = Client()
    response = client.get("/health/")
    assert response.status_code == 200
    payload = response.json()
    assert "status" in payload
    assert payload["ollama"]["ok"] in {True, False}
