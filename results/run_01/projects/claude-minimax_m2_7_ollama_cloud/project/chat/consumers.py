"""WebSocket consumer for chat streaming."""

import json

from channels.generic.websocket import AsyncWebsocketConsumer
from langchain_core.messages import AIMessage, HumanMessage

from chat.llm_service import ollama_service


class ChatConsumer(AsyncWebsocketConsumer):
    """Streams LLM responses over WebSocket with HTMX partial updates."""

    MESSAGE_TYPE_TEXT = "text"
    MESSAGE_TYPE_ERROR = "error"
    MESSAGE_TYPE_DONE = "done"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.conversation_history: list[HumanMessage | AIMessage] = []

    async def connect(self) -> None:
        self.group_name = self.channel_name
        await self.accept()

    async def disconnect(self, close_code: int) -> None:
        self.conversation_history.clear()

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        if not text_data:
            return

        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self._send_error("Invalid JSON")
            return

        user_message = data.get("message", "").strip()
        if not user_message:
            await self._send_error("Empty message")
            return

        self.conversation_history.append(HumanMessage(content=user_message))

        accumulated = ""
        try:
            async for chunk in ollama_service.stream_chat(self.conversation_history):
                accumulated += chunk
                await self._send_token(chunk)

            self.conversation_history.append(AIMessage(content=accumulated))
            await self._send_done()

        except Exception as e:
            await self._send_error(str(e))

    async def _send_token(self, token: str) -> None:
        await self.send(text_data=json.dumps({"type": self.MESSAGE_TYPE_TEXT, "content": token}))

    async def _send_error(self, message: str) -> None:
        await self.send(text_data=json.dumps({"type": self.MESSAGE_TYPE_ERROR, "content": message}))

    async def _send_done(self) -> None:
        await self.send(text_data=json.dumps({"type": self.MESSAGE_TYPE_DONE}))
