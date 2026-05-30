import json
import uuid

from channels.generic.websocket import AsyncWebsocketConsumer

from chat.services import OllamaChatService


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self) -> None:
        await self.accept()
        self.history: list[dict[str, str]] = []
        self._streaming = False
        self._group_name = f"chat_{uuid.uuid4().hex}"
        await self.channel_layer.group_add(self._group_name, self.channel_name)

    async def disconnect(self, close_code: int) -> None:
        self._streaming = False
        await self.channel_layer.group_discard(self._group_name, self.channel_name)

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        if text_data is None:
            return
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({"type": "error", "message": "Invalid JSON"}))
            return

        msg_type = data.get("type", "")
        if msg_type == "chat.message":
            await self._handle_chat_message(data.get("content", ""))
        else:
            msg = f"Unknown type: {msg_type}"
            await self.send(text_data=json.dumps({"type": "error", "message": msg}))

    async def _handle_chat_message(self, content: str) -> None:
        if not content.strip():
            await self.send(text_data=json.dumps({"type": "error", "message": "Empty message"}))
            return

        self.history.append({"role": "user", "content": content})
        await self.send(text_data=json.dumps({"type": "status", "status": "streaming"}))

        service = OllamaChatService()
        reply_parts: list[str] = []
        self._streaming = True

        try:
            async for token in service.stream(self.history):
                if not self._streaming:
                    break
                await self.send(text_data=json.dumps({"type": "token", "token": token}))
                reply_parts.append(token)
        except Exception as exc:
            msg = f"Streaming failed: {exc}"
            await self.send(text_data=json.dumps({"type": "error", "message": msg}))
            self._streaming = False
            return

        self._streaming = False
        reply = "".join(reply_parts)
        self.history.append({"role": "assistant", "content": reply})
        await self.send(text_data=json.dumps({"type": "status", "status": "done"}))
