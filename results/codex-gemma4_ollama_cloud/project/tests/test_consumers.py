import pytest
from channels.testing import WebsocketCommunicator

from core.asgi import application


@pytest.mark.asyncio
async def test_chat_consumer_echo():
    # Test WebSocket connection and message exchange
    communicator = WebsocketCommunicator(application, "/ws/chat/")
    connected, _ = await communicator.connect()
    assert connected

    # Send a message (JSON as expected by our consumer)
    await communicator.send_json_to({"message": "Hello"})
    
    # The consumer sends multiple messages: 
    # 1. User message echo
    # 2. Initial AI bubble (empty)
    # 3. AI token chunks...
    
    response = await communicator.receive_from()
    # The response contains the HTML fragment. 
    # We check for common indicators of a user message.
    assert "bg-blue-100" in response
    assert "Hello" in response
    
    await communicator.disconnect()

@pytest.mark.asyncio
async def test_chat_consumer_disconnect():
    communicator = WebsocketCommunicator(application, "/ws/chat/")
    connected, _ = await communicator.connect()
    assert connected
    
    # Trigger disconnect
    await communicator.disconnect()
    # Verifying no crash on disconnect
