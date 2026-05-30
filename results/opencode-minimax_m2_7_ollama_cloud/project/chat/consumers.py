import asyncio
import json
from typing import Any

from channels.generic.websocket import AsyncWebsocketConsumer

from .llm_service import get_ollama_service


class ChatConsumer(AsyncWebsocketConsumer):
    _active_streams: dict[str, asyncio.Task[None]] = {}

    async def connect(self) -> None:
        url_kwargs = self.scope.get("url_route", {}).get("kwargs", {})
        self.session_id: str = url_kwargs.get("session_id", "default")
        self.group_name: str = f"chat_{self.session_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code: int) -> None:
        if self.session_id in self._active_streams:
            self._active_streams[self.session_id].cancel()
            del self._active_streams[self.session_id]

        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        if text_data is None:
            return
        try:
            data: dict[str, Any] = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({"error": "Invalid JSON"}))
            return

        message = data.get("message", "")
        if not message:
            await self.send(text_data=json.dumps({"error": "No message provided"}))
            return

        system_message = {
            "role": "system",
            "content": "You are a helpful AI assistant. Keep responses concise and informative.",
        }
        user_message = {"role": "user", "content": message}
        messages = [system_message, user_message]

        async def stream_response() -> None:
            try:
                ollama_service = get_ollama_service()
                async for token in ollama_service.astream(messages):
                    response_data = {"token": token}
                    await self.channel_layer.group_send(
                        self.group_name,
                        {"type": "chat_message", "text_data": json.dumps(response_data)},
                    )
                await self.channel_layer.group_send(
                    self.group_name,
                    {"type": "chat_message", "text_data": json.dumps({"done": True})},
                )
            except Exception as e:
                error_data = {"error": str(e)}
                await self.channel_layer.group_send(
                    self.group_name,
                    {"type": "chat_message", "text_data": json.dumps(error_data)},
                )

        stream_task = asyncio.create_task(stream_response())
        self._active_streams[self.session_id] = stream_task

    async def chat_message(self, event: dict[str, Any]) -> None:
        text_data: str = event["text_data"]
        await self.send(text_data=text_data)
