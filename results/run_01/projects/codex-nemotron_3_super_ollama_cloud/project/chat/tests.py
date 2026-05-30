from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch
from channels.testing import WebsocketCommunicator
from chat.consumers import ChatConsumer
import asyncio


class IndexViewTest(TestCase):
    def test_index_view_status_code(self):
        print("Running test_index_view_status_code")
        response = self.client.get(reverse("chat:index"))
        self.assertEqual(response.status_code, 200)

    def test_index_view_template_used(self):
        print("Running test_index_view_template_used")
        response = self.client.get(reverse("chat:index"))
        self.assertTemplateUsed(response, "chat/index.html")
        self.assertTemplateUsed(response, "chat/base.html")


class ChatConsumerTest(TestCase):
    async def test_websocket_connect(self):
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), "/ws/chat/")
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)

        # Receive welcome message
        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "system")
        self.assertIn("Connected", response["message"])

        await communicator.disconnect()

    async def test_websocket_message(self):
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), "/ws/chat/")
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Skip welcome message
        welcome = await communicator.receive_json_from()
        self.assertEqual(welcome["type"], "system")

        # Define a simple async iterator
        class AsyncIterator:
            def __init__(self, items):
                self.items = items
                self.index = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.items):
                    raise StopAsyncIteration
                item = self.items[self.index]
                self.index += 1
                return item

        # Define a mock chunk class
        class MockChunk:
            def __init__(self, content):
                self.content = content

        # Create a mock for the Ollama model using MagicMock
        from unittest.mock import MagicMock

        mock_model = MagicMock()
        mock_chunks = [
            MockChunk("Hello"),
            MockChunk(", "),
            MockChunk("world"),
            MockChunk("!"),
        ]
        # Make the astream method return our async iterator
        mock_model.astream = lambda user_message: AsyncIterator(mock_chunks)

        with patch("chat.consumers.get_ollama_model") as mock_get_model:
            mock_get_model.return_value = mock_model

            # Send a test message
            test_message = "Hi"
            await communicator.send_to(text_data=test_message)

            # We expect to receive the user's message back as a chunk
            response = await communicator.receive_json_from()
            self.assertEqual(response["type"], "chunk")
            self.assertIn("html", response)
            # The HTML should contain the escaped user message
            self.assertIn("Hi", response["html"])

            # Check that the mock was called
            mock_get_model.assert_called_once()

            # Now we expect to receive the AI response chunks
            # We'll collect chunks until timeout
            received_chunks = []
            while True:
                try:
                    response = await communicator.receive_json_from(timeout=2)
                except asyncio.TimeoutError:
                    break
                if response.get("type") == "chunk":
                    received_chunks.append(response["html"])
                else:
                    # If we get a different type (like complete or error), break
                    break

            # Check that we received the expected chunks
            self.assertGreaterEqual(len(received_chunks), 1)
            # The concatenated chunks should contain the expected words
            full_html = "".join(received_chunks)
            self.assertIn("Hello", full_html)
            self.assertIn("world", full_html)
            self.assertIn("!", full_html)

        # Disconnect, ignoring any cancelled error that may occur due to test timing
        try:
            await communicator.disconnect()
        except asyncio.CancelledError:
            pass
