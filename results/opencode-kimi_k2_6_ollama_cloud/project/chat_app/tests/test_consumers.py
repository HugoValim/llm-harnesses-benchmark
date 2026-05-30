import pytest
from channels.testing import WebsocketCommunicator

from chat_app.tests.fake_streamer import FakeLlmStreamer
from chat_project.asgi import application


@pytest.fixture
def communicator() -> WebsocketCommunicator:
    return WebsocketCommunicator(application, "/ws/chat/")


@pytest.mark.django_db(transaction=True)
async def test_consumer_accepts_connection(communicator: WebsocketCommunicator) -> None:
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
async def test_consumer_streams_tokens(
    monkeypatch: pytest.MonkeyPatch,
    communicator: WebsocketCommunicator,
) -> None:
    from chat_app import consumers

    monkeypatch.setattr(consumers, "LlmStreamer", FakeLlmStreamer)

    connected, _ = await communicator.connect()
    assert connected is True

    await communicator.send_to(text_data='{"message": "hi"}')
    messages: list[str] = []
    for _ in range(20):
        msg = await communicator.receive_from()
        messages.append(msg)
        if 'data-done="true"' in msg:
            break

    assert any("hx-swap-oob" in m for m in messages)
    assert any("stream-1" in m for m in messages)
    assert any("Hello" in m for m in messages)
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
async def test_consumer_disconnect_cleans_up(communicator: WebsocketCommunicator) -> None:
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.send_to(text_data='{"message": "hello"}')
    await communicator.disconnect()
