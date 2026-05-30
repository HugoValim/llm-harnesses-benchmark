"""WebSocket consumer for chat streaming via Django Channels."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from channels.generic.websocket import AsyncWebsocketConsumer

from chat.services.llm import stream_response

logger = logging.getLogger(__name__)

STREAM_TIMEOUT = 120  # seconds — generous for long model responses


class ChatConsumer(AsyncWebsocketConsumer):
    """Streams LLM tokens to the browser over a WebSocket connection."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._streaming = False
        self._conversation: list[dict[str, str]] = []

    async def connect(self) -> None:
        await self.accept()
        logger.info("WebSocket connected: %s", self.channel_name)

    async def disconnect(self, close_code: int) -> None:
        self._streaming = False
        self._conversation.clear()
        logger.info("WebSocket disconnected: %s (code=%s)", self.channel_name, close_code)

    async def receive(self, text_data: str | None = None, **kwargs: Any) -> None:
        if text_data is None:
            return
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(json.dumps({"type": "error", "content": "Invalid JSON"}))
            return

        user_message: str = payload.get("message", "").strip()
        if not user_message:
            await self.send(json.dumps({"type": "error", "content": "Empty message"}))
            return

        self._conversation.append({"role": "human", "content": user_message})
        await self.send(json.dumps({"type": "start"}))
        self._streaming = True
        full_response = ""

        try:
            full_response = await asyncio.wait_for(self._drain_stream(), timeout=STREAM_TIMEOUT)
        except TimeoutError:
            logger.warning("Stream timed out for %s", self.channel_name)
            await self.send(json.dumps({"type": "error", "content": "LLM response timed out"}))
        except Exception:
            logger.exception("Streaming error for %s", self.channel_name)
            await self.send(
                json.dumps(
                    {
                        "type": "error",
                        "content": "LLM streaming failed — is Ollama running?",
                    }
                )
            )
        finally:
            self._streaming = False

        if full_response:
            self._conversation.append({"role": "ai", "content": full_response})

        await self.send(json.dumps({"type": "end"}))

    async def _drain_stream(self) -> str:
        """Yield tokens from the LLM and forward them to the client."""
        collected = ""
        async for token in stream_response(self._conversation):
            if not self._streaming:
                break
            collected += token
            await self.send(json.dumps({"type": "token", "content": token}))
        return collected
