"""WebSocket consumer streaming Ollama tokens to the browser.

The consumer owns the conversation history for a single socket, renders HTML
partials that HTMX swaps out-of-band into the page, and forwards each model
token as it arrives. It depends on the LLM only through
:func:`chat.services.create_chat_service`.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress

from channels.generic.websocket import AsyncWebsocketConsumer
from django.template.loader import render_to_string

from chat.services import ChatTurn, OllamaChatService, OllamaUnavailableError, create_chat_service

MESSAGES_CONTAINER_ID = "messages"
INPUT_FIELD_NAME = "message"
MAX_MESSAGE_LENGTH = 4000


class ChatConsumer(AsyncWebsocketConsumer):
    """Bridges a browser chat session to the Ollama model stream."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._history: list[ChatTurn] = []
        self._tasks: set[asyncio.Task[None]] = set()
        self._turn_counter = 0
        self._service: OllamaChatService | None = None

    async def connect(self) -> None:
        self._service = create_chat_service()
        await self.accept()

    async def disconnect(self, close_code: int) -> None:
        """Cancel any in-flight model stream and drop per-socket session state."""
        for task in list(self._tasks):
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        self._tasks.clear()
        self._history.clear()

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        prompt = self._extract_prompt(text_data)
        if prompt is None:
            return

        self._turn_counter += 1
        turn_id = self._turn_counter
        self._history.append(ChatTurn("human", prompt))

        await self._send_partial("chat/partials/user_message.html", {"content": prompt})
        await self._send_partial("chat/partials/assistant_message.html", {"turn_id": turn_id})

        task = asyncio.create_task(self._stream_reply(turn_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _extract_prompt(self, text_data: str | None) -> str | None:
        """Pull the trimmed user message out of an HTMX ws-send payload."""
        if not text_data:
            return None
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        raw = payload.get(INPUT_FIELD_NAME, "")
        if not isinstance(raw, str):
            return None
        prompt = raw.strip()[:MAX_MESSAGE_LENGTH]
        return prompt or None

    async def _stream_reply(self, turn_id: int) -> None:
        service = self._service
        if service is None:  # connect() always sets this; guard for type safety
            raise RuntimeError("stream requested before the chat service was created")
        chunks: list[str] = []
        try:
            async for token in service.astream_reply(self._history):
                chunks.append(token)
                await self._send_partial(
                    "chat/partials/token.html",
                    {"turn_id": turn_id, "token": token},
                )
        except asyncio.CancelledError:
            raise
        except OllamaUnavailableError as exc:
            await self._send_partial(
                "chat/partials/error.html",
                {"turn_id": turn_id, "detail": str(exc)},
            )
            return
        finally:
            await self._send_partial("chat/partials/stream_end.html", {"turn_id": turn_id})

        reply = "".join(chunks).strip()
        if reply:
            self._history.append(ChatTurn("ai", reply))

    async def _send_partial(self, template_name: str, context: dict[str, object]) -> None:
        html = render_to_string(template_name, context)
        await self.send(text_data=html)
