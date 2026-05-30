import pytest
from channels.testing import WebsocketCommunicator

from chat_project.asgi import application


class FakeOllamaChatService:
    def __init__(self, base_url=None, model=None):
        pass

    async def stream(self, messages):
        for token in ["Hello", " ", "world", "!"]:
            yield token


@pytest.fixture
def fake_service(monkeypatch):
    monkeypatch.setattr(
        "chat.consumers.OllamaChatService",
        FakeOllamaChatService,
    )


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_consumer_streams_tokens(fake_service):
    communicator = WebsocketCommunicator(application, "/ws/chat/")
    connected, subprotocol = await communicator.connect()
    assert connected

    await communicator.send_json_to({"type": "chat.message", "content": "hi"})

    status = await communicator.receive_json_from()
    assert status["type"] == "status"
    assert status["status"] == "streaming"

    tokens = []
    while True:
        message = await communicator.receive_json_from(timeout=2)
        if message["type"] == "token":
            tokens.append(message["token"])
        elif message["type"] == "status" and message["status"] == "done":
            break
        else:
            pytest.fail(f"Unexpected message: {message}")

    assert tokens == ["Hello", " ", "world", "!"]
    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_consumer_rejects_empty_message(fake_service):
    communicator = WebsocketCommunicator(application, "/ws/chat/")
    connected, _ = await communicator.connect()
    assert connected

    await communicator.send_json_to({"type": "chat.message", "content": "   "})
    response = await communicator.receive_json_from(timeout=2)
    assert response["type"] == "error"
    assert "Empty" in response["message"]
    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_consumer_handles_invalid_json():
    communicator = WebsocketCommunicator(application, "/ws/chat/")
    connected, _ = await communicator.connect()
    assert connected

    await communicator.send_to(text_data="not-json")
    response = await communicator.receive_json_from(timeout=2)
    assert response["type"] == "error"
    assert "Invalid JSON" in response["message"]
    await communicator.disconnect()
