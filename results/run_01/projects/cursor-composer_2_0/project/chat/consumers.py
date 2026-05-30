"""
Channels WebSocket consumer: LangChain streaming -> HTMX OOB HTML frames.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from channels.generic.websocket import AsyncWebsocketConsumer
from langchain_core.messages import BaseMessage

from chat import llm_service, ws_fragments

logger = logging.getLogger(__name__)


class ChatConsumer(AsyncWebsocketConsumer):  # type: ignore[misc]
    """Streams assistant tokens as HTMX `hx-swap-oob` HTML fragments."""

    async def connect(self) -> None:
        await self.accept()
        self.history: list[BaseMessage] = []
        self._turn = 0

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        if text_data is None:
            return

        try:
            payload: dict[str, Any] = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(
                text_data=ws_fragments.error_banner(
                    "Invalid message format (expected JSON).",
                ),
            )
            return

        if not isinstance(payload, dict):
            await self.send(text_data=ws_fragments.error_banner("Invalid message envelope."))
            return

        user_text = str(payload.get("message", "")).strip()
        if not user_text:
            await self.send(text_data=ws_fragments.error_banner("Message cannot be empty."))
            return

        await self.send(text_data=ws_fragments.clear_error())
        await self.send(text_data=ws_fragments.typing_indicator(True))

        self._turn += 1
        bubble_id = f"assistant-bubble-{self._turn}"

        await self.send(text_data=ws_fragments.user_message_row(user_text))
        await self.send(text_data=ws_fragments.assistant_shell(bubble_id))

        try:
            async for token in llm_service.stream_assistant_tokens(self.history, user_text):
                if token:
                    await self.send(text_data=ws_fragments.token_append(bubble_id, token))
        except Exception as exc:  # noqa: BLE001 — surfaced to UI, logged server-side
            logger.exception("LLM streaming failed")
            await self.send(
                text_data=ws_fragments.error_banner(
                    "The assistant could not finish this reply. "
                    f"Check that Ollama is running and reachable ({type(exc).__name__})."
                )
            )
        finally:
            await self.send(text_data=ws_fragments.typing_indicator(False))
