import pytest
from channels.testing import WebsocketCommunicator

from chat.consumers import ChatConsumer
from chat.services.llm import ChatService


class FakeChunksChatService:
    def __init__(self, chunks=None):
        self.chunks = chunks or ['Hello', ' ', 'world']

    async def stream(self, messages):
        for c in self.chunks:
            yield c


class FailingChatService:
    async def stream(self, messages):
        raise ConnectionError('Model unreachable')
        yield  # pragma: no cover — makes this an async generator


@pytest.mark.asyncio
async def test_consumer_receives_chunks():
    consumer = ChatConsumer()
    consumer.chat_service = FakeChunksChatService()
    communicator = WebsocketCommunicator(consumer, '/ws/chat/')
    connected, _ = await communicator.connect()
    assert connected

    await communicator.send_json_to({'message': 'hello'})

    user_msg = await communicator.receive_json_from()
    assert user_msg['type'] == 'user-message'
    assert user_msg['message'] == 'hello'

    info = await communicator.receive_json_from()
    assert info['type'] == 'info'

    for expected in ['Hello', ' ', 'world']:
        chunk = await communicator.receive_json_from()
        assert chunk['type'] == 'chunk'
        assert chunk['content'] == expected

    done = await communicator.receive_json_from()
    assert done['type'] == 'done'

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_consumer_sends_error_on_failure():
    consumer = ChatConsumer()
    consumer.chat_service = FailingChatService()
    communicator = WebsocketCommunicator(consumer, '/ws/chat/')
    connected, _ = await communicator.connect()
    assert connected

    await communicator.send_json_to({'message': 'hello'})

    await communicator.receive_json_from()  # user message
    await communicator.receive_json_from()  # info
    error = await communicator.receive_json_from()
    assert error['type'] == 'error'
    assert 'Model unreachable' in error['message']

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_consumer_empty_message():
    consumer = ChatConsumer()
    communicator = WebsocketCommunicator(consumer, '/ws/chat/')
    connected, _ = await communicator.connect()
    assert connected

    await communicator.send_json_to({'message': '   '})
    # No response expected — consumer should return early

    await communicator.disconnect()


@pytest.fixture
def patch_chat_service(monkeypatch):
    def _patch(chunks=None):
        fake = FakeChunksChatService(chunks)
        monkeypatch.setattr(ChatService, 'stream', fake.stream)
        return fake

    return _patch
