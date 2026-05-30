"""
WebSocket consumer for chat streaming.
"""

import asyncio
import contextlib
from typing import Any

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from chatapp.llm_service import get_chat_model


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """Async WebSocket consumer for streaming LLM responses."""

    chat_history: list[dict[str, str]]
    stream_task: asyncio.Task[Any] | None
    is_streaming: bool

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.chat_history = []
        self.stream_task = None
        self.is_streaming = False

    async def connect(self) -> None:
        """Accept WebSocket connection."""
        await self.accept()
        await self.send_json({"type": "connected", "message": "Connected to chat"})

    async def disconnect(self, close_code: int) -> None:
        """Clean up on disconnect - cancel streaming and clear state."""
        self.is_streaming = False
        if self.stream_task and not self.stream_task.done():
            self.stream_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.stream_task
        self.chat_history.clear()

    async def receive_json(self, data: dict[str, Any]) -> None:
        """Handle incoming JSON message from client."""
        message = data.get("message", "")

        if not message:
            await self.send_json({"type": "error", "message": "Empty message"})
            return

        self.chat_history.append({"role": "user", "content": message})

        await self.send_json({"type": "stream_start"})

        try:
            llm = get_chat_model()
            self.is_streaming = True
            full_response = ""

            async for chunk in llm.astream(self.chat_history):
                if not self.is_streaming:
                    break
                content = chunk.content if hasattr(chunk, "content") else str(chunk)
                if content:
                    full_response += str(content)
                    await self.send_json(
                        {
                            "type": "stream_chunk",
                            "content": content,
                        }
                    )

            self.chat_history.append({"role": "assistant", "content": full_response})
            await self.send_json(
                {
                    "type": "stream_end",
                    "full_response": full_response,
                }
            )

        except Exception as e:
            error_msg = str(e)
            if "connection" in error_msg.lower() or "refused" in error_msg.lower():
                error_msg = "Ollama server unreachable. Ensure Ollama is running."
            await self.send_json(
                {
                    "type": "error",
                    "message": error_msg,
                }
            )
