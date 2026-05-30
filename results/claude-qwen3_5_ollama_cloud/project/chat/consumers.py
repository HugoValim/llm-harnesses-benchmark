"""
WebSocket consumers for real-time chat streaming.
"""

import json
import logging
from typing import Any

from channels.generic.websocket import AsyncWebsocketConsumer

from .services.llm import get_llm_service

logger = logging.getLogger(__name__)


class ChatConsumer(AsyncWebsocketConsumer):
    """
    Async WebSocket consumer for streaming chat responses.

    Handles:
    - WebSocket connect/disconnect
    - Message reception and LLM streaming
    - Multi-turn conversation context (in-memory per connection)
    - Error handling and user-friendly error messages
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.conversation_history: list[dict[str, str]] = []
        self.llm_service = get_llm_service()

    async def send_json_impl(self, data: dict[str, Any]):
        """Send a JSON message over the WebSocket."""
        await self.send(text_data=json.dumps(data))

    async def connect(self):
        """Accept the WebSocket connection."""
        await self.accept()
        try:
            logger.info(f"WebSocket connected: {self.channel_name}")
        except AttributeError:
            logger.info("WebSocket connected")
        # Send initial connection acknowledgment
        await self.send_json_impl(
            {
                "type": "connection_ack",
                "message": "Connected to chat server",
            }
        )

    async def disconnect(self, code: int):
        """Handle WebSocket disconnect - clear conversation history."""
        try:
            logger.info(f"WebSocket disconnected (code={code})")
        except AttributeError:
            # channel_name not available in tests
            logger.info(f"WebSocket disconnected (code={code})")
        self.conversation_history.clear()

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None):  # noqa: ARG002
        """
        Handle incoming WebSocket messages.

        Expects JSON with 'message' key containing user input.
        Streams LLM response token-by-token.
        """
        if text_data is None:
            return

        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send_json_impl(
                {
                    "type": "error",
                    "message": "Invalid JSON format",
                }
            )
            return

        user_message = data.get("message", "").strip()
        if not user_message:
            await self.send_json_impl(
                {
                    "type": "error",
                    "message": "Empty message received",
                }
            )
            return

        # Add user message to conversation history
        self.conversation_history.append(
            {
                "role": "human",
                "content": user_message,
            }
        )

        # Start streaming the LLM response
        await self._stream_llm_response()

    async def _stream_llm_response(self):
        """Stream LLM response tokens to the WebSocket."""
        try:
            # Signal start of response
            await self.send_json_impl(
                {
                    "type": "response_start",
                }
            )

            accumulated_content = ""

            async for token in self.llm_service.stream_response(self.conversation_history):
                accumulated_content += token
                # Stream each token as it arrives
                await self.send_json_impl(
                    {
                        "type": "token",
                        "content": token,
                    }
                )

            # Store AI response in conversation history for multi-turn context
            if accumulated_content:
                self.conversation_history.append(
                    {
                        "role": "ai",
                        "content": accumulated_content,
                    }
                )

            # Signal end of response
            await self.send_json_impl(
                {
                    "type": "response_end",
                    "complete_message": accumulated_content,
                }
            )

        except ConnectionError as e:
            logger.error(f"LLM connection failed: {e}")
            await self.send_json_impl(
                {
                    "type": "error",
                    "message": (
                        "Cannot connect to Ollama. "
                        "Ensure Ollama is running (ollama serve) and the model is pulled "
                        "(ollama pull qwen2.5:7b)."
                    ),
                    "code": "ollama_unreachable",
                }
            )
        except RuntimeError as e:
            logger.error(f"LLM streaming failed: {e}")
            await self.send_json_impl(
                {
                    "type": "error",
                    "message": f"Streaming failed: {str(e)}",
                    "code": "streaming_error",
                }
            )
        except Exception as e:
            logger.exception(f"Unexpected error streaming LLM response: {e}")
            await self.send_json_impl(
                {
                    "type": "error",
                    "message": "An unexpected error occurred. Please try again.",
                    "code": "internal_error",
                }
            )
