import os

# Set environment variables before importing Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "chatproject.settings")
os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key-for-testing-purposes-only")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-purposes-only")
os.environ.setdefault("OLLAMA_HOST", "http://localhost:11434")
os.environ.setdefault("OLLAMA_MODEL", "qwen2.5:7b")

from django.test import TestCase, SimpleTestCase
from channels.testing import WebsocketCommunicator
from chat.consumers import ChatConsumer
from chat.services import OllamaService
from unittest.mock import patch


class ChatViewTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Ensure SECRET_KEY is set for all tests
        if not os.environ.get("SECRET_KEY"):
            os.environ["SECRET_KEY"] = "test-secret-key-for-testing-purposes-only"
        if not os.environ.get("DJANGO_SECRET_KEY"):
            os.environ["DJANGO_SECRET_KEY"] = (
                "test-secret-key-for-testing-purposes-only"
            )

    def test_chat_view_status_code(self):
        """Test that the chat view returns a 200 status code"""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_chat_view_template_used(self):
        """Test that the chat view uses the correct template"""
        response = self.client.get("/")
        self.assertTemplateUsed(response, "chat/chat.html")


class ChatConsumerTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Ensure SECRET_KEY is set for all tests
        if not os.environ.get("SECRET_KEY"):
            os.environ["SECRET_KEY"] = "test-secret-key-for-testing-purposes-only"
        if not os.environ.get("DJANGO_SECRET_KEY"):
            os.environ["DJANGO_SECRET_KEY"] = (
                "test-secret-key-for-testing-purposes-only"
            )

    async def test_websocket_connect_and_receive(self):
        """Test WebSocket connection and message handling with mocked Ollama service"""

        # Create a mock stream response
        async def mock_stream_response(*args, **kwargs):
            for chunk in ["Hello", " ", "world", "!"]:
                yield chunk

        # We'll patch the OllamaService directly in the consumer
        with patch(
            "chat.services.OllamaService.stream_response",
            side_effect=mock_stream_response,
        ):
            communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), "/ws/chat/")

            # Connect to the WebSocket
            connected, subprotocol = await communicator.connect()
            self.assertTrue(connected)

            # Send a message
            await communicator.send_json_to({"message": "Hello world"})

            # Receive user message echo
            response = await communicator.receive_json_from()
            self.assertEqual(response["type"], "user_message")
            self.assertEqual(response["message"], "Hello world")

            # Receive streaming chunks
            chunks_received = []
            for i in range(4):  # Expect 4 chunks
                response = await communicator.receive_json_from()
                if response["type"] == "assistant_chunk":
                    chunks_received.append(response["chunk"])

            # Verify we received the expected chunks
            self.assertEqual(chunks_received, ["Hello", " ", "world", "!"])

            # Receive completion signal
            response = await communicator.receive_json_from()
            self.assertEqual(response["type"], "assistant_complete")
            self.assertEqual(response["message"], "Hello world!")

            await communicator.disconnect()


class ChatServiceTest(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Ensure SECRET_KEY is set for all tests
        if not os.environ.get("SECRET_KEY"):
            os.environ["SECRET_KEY"] = "test-secret-key-for-testing-purposes-only"
        if not os.environ.get("DJANGO_SECRET_KEY"):
            os.environ["DJANGO_SECRET_KEY"] = (
                "test-secret-key-for-testing-purposes-only"
            )
        if not os.environ.get("OLLAMA_HOST"):
            os.environ["OLLAMA_HOST"] = "http://localhost:11434"
        if not os.environ.get("OLLAMA_MODEL"):
            os.environ["OLLAMA_MODEL"] = "qwen2.5:7b"

    def test_ollama_service_initialization(self):
        """Test that OllamaService initializes correctly"""
        service = OllamaService()

        # Check that environment variables are used with defaults
        self.assertEqual(service.model, "qwen2.5:7b")
        self.assertEqual(service.base_url, "http://localhost:11434")
