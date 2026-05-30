from __future__ import annotations

import json

import httpx
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

from chat.llm import Conversation, create_chat_client, stream_response

_ERROR_BOX = "bg-red-900 rounded-2xl px-4 py-2 max-w-[80%] text-red-200"
_ASSIST_BOX = "bg-gray-800 rounded-2xl px-4 py-2 max-w-[80%] whitespace-pre-wrap"


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class ChatConsumer(AsyncWebsocketConsumer):  # type: ignore[misc]
    async def connect(self) -> None:
        await self.accept()
        self.conversation = Conversation()
        self.msg_counter = 0

    async def disconnect(self, code: int) -> None:
        pass

    async def receive(self, text_data: str | None = None) -> None:
        if not text_data:
            return
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(
                text_data=(
                    f'<div class="flex justify-start"><div class="{_ERROR_BOX}">Invalid message format</div></div>'
                )
            )
            return

        message = data.get("message", "").strip()
        if not message:
            return

        self.conversation.add("user", message)

        client = create_chat_client(
            base_url=settings.OLLAMA_HOST,
            model=settings.OLLAMA_MODEL,
        )

        msg_id = f"msg-{self.msg_counter}"
        self.msg_counter += 1

        assistant_content = ""
        first = True
        try:
            async for chunk in stream_response(client, self.conversation):
                assistant_content += chunk
                if first:
                    html = (
                        f'<div id="{msg_id}" class="flex justify-start">'
                        f'<div id="{msg_id}-content" class="{_ASSIST_BOX}">'
                        f"{_esc(chunk)}</div></div>"
                    )
                    await self.send(text_data=html)
                    first = False
                else:
                    html = (
                        f'<div id="{msg_id}-content" '
                        f'hx-swap-oob="innerHTML" '
                        f'class="{_ASSIST_BOX}">'
                        f"{_esc(assistant_content)}</div>"
                    )
                    await self.send(text_data=html)
        except httpx.ConnectError:
            html = self._error_html(msg_id, first, "Unable to reach Ollama. Is it running?")
            await self.send(text_data=html)
            return
        except Exception as exc:
            html = self._error_html(msg_id, first, f"Streaming error: {exc}")
            await self.send(text_data=html)
            return

        self.conversation.add("assistant", assistant_content)

    @staticmethod
    def _error_html(msg_id: str, first: bool, text: str) -> str:
        escaped = _esc(text)
        if first:
            return (
                f'<div id="{msg_id}" class="flex justify-start">'
                f'<div id="{msg_id}-content" class="{_ERROR_BOX}">'
                f"{escaped}</div></div>"
            )
        return f'<div id="{msg_id}-content" hx-swap-oob="innerHTML" class="{_ERROR_BOX}">{escaped}</div>'
