import pytest

from .conftest import FailingChatOllama, FakeChatOllama


@pytest.mark.asyncio
async def test_stream_returns_chunks(fake_ollama):
    chunks = []
    async for chunk in fake_ollama.astream([('user', 'hello')]):
        chunks.append(chunk.content)
    assert chunks == ['Hello', ' ', 'world', '!']


@pytest.mark.asyncio
async def test_stream_custom_chunks(fake_ollama_chunks):
    llm = FakeChatOllama(chunks=fake_ollama_chunks)
    chunks = []
    async for chunk in llm.astream([('user', 'hi')]):
        chunks.append(chunk.content)
    assert chunks == ['Hello', ' ', 'from', ' ', 'Ollama', '!']


@pytest.mark.asyncio
async def test_stream_failure():
    llm = FailingChatOllama()
    with pytest.raises(ConnectionError, match='Connection refused'):
        async for _ in llm.astream([('user', 'hi')]):
            pass
