import asyncio
import json
import uuid
from contextlib import suppress
from json import JSONDecodeError
from typing import cast

from channels.generic.websocket import AsyncWebsocketConsumer

from chat.llm import build_chat_streamer
from chat.messages import ChatTurn
from chat.partials import render_html


class ChatConsumer(AsyncWebsocketConsumer):
    conversation: list[ChatTurn]
    group_name: str
    stream_task: asyncio.Task[None] | None
    closed: bool

    async def connect(self) -> None:
        self.conversation = []
        self.group_name = f"chat-{uuid.uuid4().hex}"
        self.stream_task = None
        self.closed = False
        if self.channel_layer is not None:
            await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code: int) -> None:
        self.closed = True
        await self._cancel_active_stream()
        if self.channel_layer is not None:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(
        self,
        text_data: str | None = None,
        bytes_data: bytes | None = None,
    ) -> None:
        if self.stream_task is not None and not self.stream_task.done():
            await self._send_error("A reply is still streaming; wait for it to finish.")
            return
        try:
            prompt = parse_prompt(text_data)
        except ValueError as error:
            await self._send_error(str(error))
            return
        await self._send_user_message(prompt)
        self.stream_task = asyncio.create_task(self._stream_assistant_reply(prompt))
        await self._await_active_stream()

    async def _stream_assistant_reply(self, prompt: str) -> None:
        self.conversation.append(ChatTurn(role="user", content=prompt))
        message_id = f"msg-{uuid.uuid4().hex}"
        await self._send_assistant_shell(message_id)
        reply_parts: list[str] = []
        try:
            streamer = build_chat_streamer()
            async for token in streamer.stream_reply(tuple(self.conversation)):
                reply_parts.append(token)
                await self._send_token(message_id, token)
        except Exception:
            await self._send_error(
                "Ollama streaming failed; check Ollama host and model."
            )
            return
        self.conversation.append(
            ChatTurn(role="assistant", content="".join(reply_parts))
        )

    async def _await_active_stream(self) -> None:
        if self.stream_task is None:
            return
        try:
            await self.stream_task
        finally:
            self.stream_task = None

    async def _cancel_active_stream(self) -> None:
        if self.stream_task is None or self.stream_task.done():
            return
        self.stream_task.cancel()
        with suppress(asyncio.CancelledError):
            await self.stream_task

    async def _send_user_message(self, prompt: str) -> None:
        html = await render_html(
            "chat/partials/append_message.html",
            {
                "message_id": f"msg-{uuid.uuid4().hex}",
                "role": "user",
                "content": prompt,
            },
        )
        await self.send(text_data=html)

    async def _send_assistant_shell(self, message_id: str) -> None:
        html = await render_html(
            "chat/partials/append_message.html",
            {"message_id": message_id, "role": "assistant", "content": ""},
        )
        await self.send(text_data=html)

    async def _send_token(self, message_id: str, token: str) -> None:
        html = await render_html(
            "chat/partials/append_token.html",
            {"message_id": message_id, "token": token},
        )
        await self.send(text_data=html)

    async def _send_error(self, detail: str) -> None:
        html = await render_html(
            "chat/partials/append_error.html",
            {"message_id": f"msg-{uuid.uuid4().hex}", "content": detail},
        )
        await self.send(text_data=html)


def parse_prompt(text_data: str | None) -> str:
    """Extract a non-empty message from an HTMX WebSocket payload.

    Example:
        prompt = parse_prompt('{"message": "Hi"}')
    """
    if text_data is None:
        raise ValueError("message payload None invalid; expected JSON object.")
    payload = _json_payload(text_data)
    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ValueError(f"message={message!r} invalid; expected non-empty string.")
    return message.strip()


def _json_payload(text_data: str) -> dict[str, object]:
    try:
        payload: object = json.loads(text_data)
    except JSONDecodeError as error:
        raise ValueError("message payload invalid JSON; expected object.") from error
    if not isinstance(payload, dict):
        shape = type(payload).__name__
        raise ValueError(f"message payload type={shape!r} invalid; expected object.")
    if not all(isinstance(key, str) for key in payload):
        raise ValueError("message payload keys invalid; expected string keys.")
    return cast(dict[str, object], payload)
