import html
import json
import urllib.parse
from typing import Any

from channels.generic.websocket import AsyncWebsocketConsumer

from chat_app.services import LlmStreamer


class ChatConsumer(AsyncWebsocketConsumer):  # type: ignore[misc]
    """WebSocket consumer that streams LLM tokens as HTMX OOB partials."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.history: list[dict[str, str]] = []
        self.active = False
        self.turn = 0

    async def connect(self) -> None:
        await self.accept()

    async def disconnect(self, close_code: int) -> None:
        self.active = False
        self.history.clear()

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        if not text_data:
            return
        data = self._parse_message(text_data)
        if data is None:
            await self._send_error("Invalid message")
            return

        user_message = data.get("message", "").strip()
        if not user_message:
            await self._send_error("Empty message")
            return

        self.history.append({"role": "user", "content": user_message})
        self.turn += 1
        turn_id = f"stream-{self.turn}"

        await self.send(
            text_data=(
                f'<div hx-swap-oob="beforeend:#messages" class="user-message">'
                f'<div class="bubble">{html.escape(user_message)}</div></div>'
            ),
        )
        await self.send(
            text_data=(
                f'<div hx-swap-oob="beforeend:#messages" class="assistant-message">'
                f'<div class="bubble" id="{turn_id}"></div></div>'
            ),
        )

        self.active = True
        streamer = LlmStreamer()
        assistant_parts: list[str] = []
        try:
            async for token in streamer.astream(self.history):
                if not self.active:
                    break
                assistant_parts.append(token)
                await self.send(
                    text_data=(
                        f'<span hx-swap-oob="beforeend:#{turn_id}">{html.escape(token)}</span>'
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            await self._send_error(f"Streaming error: {exc}")
        finally:
            self.active = False
            assistant_message = "".join(assistant_parts)
            if assistant_message:
                self.history.append({"role": "assistant", "content": assistant_message})
            await self.send(text_data='<span hx-swap-oob="none" data-done="true"></span>')

    def _parse_message(self, text_data: str) -> dict[str, str] | None:
        try:
            parsed = json.loads(text_data)
        except json.JSONDecodeError:
            parsed = urllib.parse.parse_qs(text_data)
            if "message" in parsed:
                return {"message": parsed["message"][0]}
            return None
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items() if isinstance(k, str)}
        return None

    async def _send_error(self, message: str) -> None:
        await self.send(
            text_data=(
                f'<div hx-swap-oob="beforeend:#messages" class="error-message">'
                f"{html.escape(message)}"
                f"</div>"
            ),
        )
