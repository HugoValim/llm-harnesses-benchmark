import json

from channels.generic.websocket import AsyncWebsocketConsumer

from chat.llm import stream_response


class ChatConsumer(AsyncWebsocketConsumer):
    groups: list[str] = []

    async def connect(self) -> None:
        self.conversation: list[dict[str, str]] = []
        self.stream_active = False
        await self.accept()

    async def disconnect(self, close_code: int) -> None:
        self.stream_active = False
        self.conversation.clear()

    async def receive(
        self, text_data: str | None = None, bytes_data: bytes | None = None
    ) -> None:
        if text_data is None:
            return
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(json.dumps({"type": "error", "content": "Invalid JSON"}))
            return

        user_message = payload.get("message", "").strip()
        if not user_message:
            return

        self.conversation.append({"role": "user", "content": user_message})
        self.stream_active = True

        full_response: list[str] = []
        try:
            async for token in stream_response(self.conversation):
                if not self.stream_active:
                    break
                full_response.append(token)
                await self.send(json.dumps({"type": "token", "content": token}))
        except Exception as exc:
            await self.send(
                json.dumps({"type": "error", "content": f"Streaming error: {exc}"})
            )
            return

        assistant_message = "".join(full_response)
        self.conversation.append({"role": "assistant", "content": assistant_message})
        await self.send(json.dumps({"type": "done", "content": assistant_message}))
