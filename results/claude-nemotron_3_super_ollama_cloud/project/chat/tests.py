from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch, AsyncMock
from channels.testing import WebsocketCommunicator
from chat.consumers import ChatConsumer

class HomePageTest(TestCase):
    def test_home_page_returns_200(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

class ChatConsumerTest(TestCase):
    async def test_websocket_connection(self):
        # Mock the OllamaService to avoid actual network calls
        with patch('chat.consumers.OllamaService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            
            # Mock the stream_response method to return a fake stream
            async def mock_stream(*args, **kwargs):
                yield "Hello"
                yield " "
                yield "world"
                yield "!"
            
            mock_service.stream_response = mock_stream
            
            communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), "ws/chat/")
            connected, subprotocol = await communicator.connect()
            self.assertTrue(connected)

            # Receive the welcome message
            welcome_response = await communicator.receive_json_from()
            self.assertEqual(welcome_response["message"], "Hello! How can I assist you today?")
            self.assertEqual(welcome_response["type"], "system")

            # Send a message
            await communicator.send_json_to({
                "message": "Hello"
            })

            # Receive multiple chunks
            chunks = []
            while True:
                try:
                    response = await communicator.receive_json_from()
                    if response["type"] == "end":
                        break
                    chunks.append(response["message"])
                except TimeoutError:
                    break
            
            full_response = "".join(chunks)
            self.assertEqual(full_response, "Hello world!")

            await communicator.disconnect()
