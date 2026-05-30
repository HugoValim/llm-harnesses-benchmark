from unittest.mock import AsyncMock, MagicMock

import pytest

from chat.services.llm import ChatService


@pytest.mark.asyncio
async def test_stream_chat_success():
    # Mock ChatOllama
    mock_client = MagicMock()
    
    # astream must be an async function that returns an async iterator
    async def mock_astream(messages):
        yield MagicMock(content="Hello")
        yield MagicMock(content=" world")
        yield MagicMock(content="!")
    
    mock_client.astream = mock_astream
    
    service = ChatService()
    service.client = mock_client
    
    chunks = []
    async for token in service.stream_chat([], "Hi"):
        chunks.append(token)
        
    assert "".join(chunks) == "Hello world!"

@pytest.mark.asyncio
async def test_stream_chat_error():
    mock_client = MagicMock()
    
    async def mock_astream_error(messages):
        raise Exception("Ollama Down")
        yield # make it a generator
    
    mock_client.astream = mock_astream_error
    
    service = ChatService()
    service.client = mock_client
    
    chunks = []
    async for token in service.stream_chat([], "Hi"):
        chunks.append(token)
        
    assert "[Error]: Ollama Down" in "".join(chunks)
