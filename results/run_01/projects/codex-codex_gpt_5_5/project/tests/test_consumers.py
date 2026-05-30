import pytest
from channels.testing import WebsocketCommunicator

from chat.messages import ChatTurn
from chatstream.asgi import application
from tests.fakes import FakeStreamingClient


async def receive_frames(
    communicator: WebsocketCommunicator,
    count: int,
) -> list[str]:
    return [await communicator.receive_from() for _ in range(count)]


def make_communicator() -> WebsocketCommunicator:
    headers = [(b"host", b"testserver"), (b"origin", b"http://testserver")]
    return WebsocketCommunicator(application, "/ws/chat/", headers=headers)


@pytest.mark.asyncio
async def test_consumer_streams_multiple_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_streamer = FakeStreamingClient([["Hel", "lo"]])
    monkeypatch.setattr("chat.consumers.build_chat_streamer", lambda: fake_streamer)
    communicator = make_communicator()

    connected, _ = await communicator.connect()
    assert connected
    await communicator.send_json_to({"message": "Hello"})
    frames = await receive_frames(communicator, 4)
    await communicator.disconnect()

    assert "Hello" in frames[0]
    assert "assistant-content-" in frames[1]
    assert "Hel" in frames[2]
    assert "lo" in frames[3]
    assert fake_streamer.calls[0] == (ChatTurn(role="user", content="Hello"),)


@pytest.mark.asyncio
async def test_consumer_keeps_multi_turn_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_streamer = FakeStreamingClient([["One"], ["Two"]])
    monkeypatch.setattr("chat.consumers.build_chat_streamer", lambda: fake_streamer)
    communicator = make_communicator()

    connected, _ = await communicator.connect()
    assert connected
    await communicator.send_json_to({"message": "First"})
    await receive_frames(communicator, 3)
    await communicator.send_json_to({"message": "Second"})
    await receive_frames(communicator, 3)
    await communicator.disconnect()

    assert fake_streamer.calls[1] == (
        ChatTurn(role="user", content="First"),
        ChatTurn(role="assistant", content="One"),
        ChatTurn(role="user", content="Second"),
    )


@pytest.mark.asyncio
async def test_consumer_surfaces_stream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_streamer = FakeStreamingClient([["ignored"]], fail=True)
    monkeypatch.setattr("chat.consumers.build_chat_streamer", lambda: fake_streamer)
    communicator = make_communicator()

    connected, _ = await communicator.connect()
    assert connected
    await communicator.send_json_to({"message": "Hello"})
    frames = await receive_frames(communicator, 3)
    await communicator.disconnect()

    assert "Ollama streaming failed" in frames[2]
