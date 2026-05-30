from unittest.mock import AsyncMock, MagicMock

import pytest
from channels.testing import WebsocketCommunicator

from django.urls import reverse

from chat.consumers import ChatConsumer
from chat.services import LLMService


@pytest.mark.asyncio
async def test_llm_service_streaming():
    # Mock astoream to actually be an async generator
    async def mock_astream(*args, **kwargs):
        yield MagicMock(content="Hello")
        yield MagicMock(content=" world")
        yield MagicMock(content="!")

    mock_llm = MagicMock()
    mock_llm.astream = mock_astream
    
    service = LLMService()
    service.llm = mock_llm
    
    chunks = []
    async for token in service.stream_chat("Hi", []):
        chunks.append(token)
    
    assert chunks == ["Hello", " world", "!"]

@pytest.mark.asyncio
async def test_chat_consumer_streaming():
    mock_service = MagicMock()
    async def mock_stream(prompt, history):
        yield "chunk1"
        yield "chunk2"
    
    mock_service.stream_chat = mock_stream
    
    communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), "/ws/chat/")
    connected, _ = await communicator.connect()
    assert connected
    
    # Instead of accessing .consumer, we send data and check responses
    await communicator.send_json_to({"prompt": "Testing"})
    
    response1 = await communicator.receive_json_from()
    assert response1["type"] == "message"
    
    response2 = await communicator.receive_json_from()
    assert response2["type"] == "token"
    assert response2["content"] == "chunk1"
    
    response3 = await communicator.receive_json_from()
    assert response3["type"] == "token"
    assert response3["content"] == "chunk2"
    
    response4 = await communicator.receive_json_from()
    assert response4["type"] == "done"
    
    await communicator.disconnect()



def test_index_view(client):
    url = reverse("index")
    response = client.get(url)
    assert response.status_code == 200
    assert 'hx-ext="ws connect:/ws/chat/"' in response.content.decode()
    assert "ws-send" in response.content.decode()


def test_health_view(client):
    url = reverse("health")
    response = client.get(url)
    assert response.status_code == 200
