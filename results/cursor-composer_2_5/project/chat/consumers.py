"""WebSocket consumer streaming Ollama tokens to HTMX."""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from typing import Any

from channels.generic.websocket import AsyncWebsocketConsumer
from django.template.loader import render_to_string
from langchain_core.messages import BaseMessage

from chat.services import llm


class ChatConsumer(AsyncWebsocketConsumer):  # type: ignore[misc]
    """Stream assistant tokens over WebSocket as HTMX OOB HTML fragments."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._history: list[BaseMessage] = []
        self._stream_task: asyncio.Task[None] | None = None
        self._session_id: str | None = None

    async def connect(self) -> None:
        self._session_id = uuid.uuid4().hex
        await self.accept()

    async def disconnect(self, close_code: int) -> None:
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._stream_task
        self._history.clear()
        self._stream_task = None
        self._session_id = None

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        if not text_data:
            return
        if self._stream_task and not self._stream_task.done():
            await self._send_error("A response is still streaming. Please wait.")
            return

        payload = _parse_payload(text_data)
        user_text = str(payload.get("message", "")).strip()
        if not user_text:
            await self._send_error("Message cannot be empty.")
            return

        self._stream_task = asyncio.create_task(self._handle_message(user_text))

    async def _handle_message(self, user_text: str) -> None:
        message_id = uuid.uuid4().hex[:12]
        await self.send(
            text_data=render_to_string(
                "chat/partials/user_message.html",
                {"content": user_text},
            )
        )
        await self.send(
            text_data=render_to_string(
                "chat/partials/assistant_message_start.html",
                {"message_id": message_id},
            )
        )

        collected: list[str] = []
        try:
            async for token in llm.stream_chat_tokens(self._history, user_text):
                collected.append(token)
                await self.send(
                    text_data=render_to_string(
                        "chat/partials/assistant_token.html",
                        {"message_id": message_id, "token": token},
                    )
                )
        except Exception as exc:  # noqa: BLE001 - surface provider errors to UI
            await self._send_error(f"Streaming failed: {exc}")
            return

        assistant_text = "".join(collected)
        llm.append_turn(self._history, user_text, assistant_text)
        await self.send(
            text_data=render_to_string(
                "chat/partials/assistant_message_end.html",
                {"message_id": message_id},
            )
        )

    async def _send_error(self, detail: str) -> None:
        await self.send(
            text_data=render_to_string(
                "chat/partials/error_message.html",
                {"detail": detail},
            )
        )


def _parse_payload(text_data: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text_data)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        body = parsed.get("body")
        if isinstance(body, dict) and "message" in body:
            return {"message": body["message"]}
        if "message" in parsed:
            return {"message": parsed["message"]}
    if "=" in text_data:
        from urllib.parse import parse_qs

        query = parse_qs(text_data, keep_blank_values=True)
        message_values = query.get("message")
        if message_values:
            return {"message": message_values[0]}
    return {"message": text_data}
