from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from chat.llm import Conversation, create_chat_client, stream_response


def test_conversation_add():
    conv = Conversation()
    conv.add("user", "Hello")
    conv.add("assistant", "Hi there")
    assert len(conv.messages) == 2
    assert conv.messages[0].role == "user"
    assert conv.messages[0].content == "Hello"


def test_conversation_to_langchain_messages():
    conv = Conversation()
    conv.add("user", "Hi")
    conv.add("assistant", "Hello")
    msgs = conv.to_langchain_messages()
    assert msgs == [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
    ]


def test_create_chat_client():
    client = create_chat_client("http://localhost:11434", "qwen2.5:7b")
    assert client.model == "qwen2.5:7b"


@pytest.mark.asyncio
async def test_stream_response_yields_chunks():
    fake_chunks_content = ["Hello", " world", "!"]

    class FakeChunk:
        def __init__(self, content: str):
            self.content = content

    fake_client = AsyncMock()
    fake_client.astream = AsyncMock()

    async def mock_astream(messages):
        for chunk_text in fake_chunks_content:
            yield FakeChunk(chunk_text)

    fake_client.astream = mock_astream

    conv = Conversation()
    conv.add("user", "Hi")

    results = []
    async for chunk in stream_response(fake_client, conv):
        results.append(chunk)

    assert results == ["Hello", " world", "!"]
