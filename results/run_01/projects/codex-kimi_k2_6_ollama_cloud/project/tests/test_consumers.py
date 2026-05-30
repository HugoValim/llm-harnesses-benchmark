from typing import Any

import pytest
from channels.testing import WebsocketCommunicator

from chat.consumers import ChatConsumer


@pytest.fixture
def fake_service(monkeypatch: Any) -> list[str]:
    tokens = ["Hello", " ", "world"]

    async def fake_stream(history: list[dict[str, str]]) -> Any:
        for tok in tokens:
            yield tok

    monkeypatch.setattr("chat.consumers.stream_reply", fake_stream)
    return tokens


@pytest.mark.asyncio
async def test_consumer_stream(fake_service: list[str]) -> None:
    comm = WebsocketCommunicator(ChatConsumer.as_asgi(), "/ws/chat/")
    connected, _ = await comm.connect()
    assert connected

    await comm.send_json_to({"message": "hi"})

    messages = []
    for _ in range(10):
        msg = await comm.receive_json_from(timeout=2)
        messages.append(msg)
        if msg.get("type") == "bot_end":
            break

    await comm.disconnect()

    types = [m["type"] for m in messages]
    assert "user_message" in types
    assert "bot_start" in types
    assert "bot_end" in types
    tokens = [m["content"] for m in messages if m["type"] == "bot_token"]
    assert len(tokens) >= 3
    assert "".join(tokens) == "Hello world"
