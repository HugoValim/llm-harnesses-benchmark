"""
WebSocket consumers for chat streaming.
"""

import json
from typing import Any

from channels.generic.websocket import AsyncWebsocketConsumer

from .llm_service import LLMService


class ChatConsumer(AsyncWebsocketConsumer):
    """Async WebSocket consumer for streaming chat responses."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.llm_service = LLMService()
        self.is_streaming = False

    async def connect(self) -> None:
        """Accept WebSocket connection."""
        await self.accept()
        await self.send_json({"type": "connected"})

    async def disconnect(self, close_code: int) -> None:
        """Clean up on disconnect."""
        self.is_streaming = False
        self.llm_service.clear_history()

    async def receive(self, text_data: str) -> None:
        """Handle incoming message."""
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send_json({"type": "error", "message": "Invalid JSON"})
            return

        message = data.get("message", "").strip()
        if not message:
            await self.send_json({"type": "error", "message": "Empty message"})
            return

        system_prompt = data.get("system_prompt")

        if self.is_streaming:
            await self.send_json({"type": "error", "message": "Already streaming"})
            return

        self.is_streaming = True
        full_response = ""

        try:
            async for token in self.llm_service.stream_response(message, system_prompt):
                full_response += token
                await self.send_json({"type": "token", "content": token})

            await self.send_json({"type": "complete", "content": full_response})
        except Exception as e:
            await self.send_json({"type": "error", "message": str(e)})
        finally:
            self.is_streaming = False

    async def send_json(self, data: dict[str, Any]) -> None:
        """Send JSON message."""
        await self.send(text_data=json.dumps(data))
