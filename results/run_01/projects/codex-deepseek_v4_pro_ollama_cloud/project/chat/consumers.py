"""AsyncWebsocketConsumer for real-time chat streaming via HTMX WebSocket extension."""

from channels.generic.websocket import AsyncWebsocketConsumer

from chat.services import LLMError, stream_chat


class ChatConsumer(AsyncWebsocketConsumer):
    """Handles ws:// chat messages — streams LLM tokens to browser via HTMX ws."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._conversation: list[dict[str, str]] = []

    async def connect(self) -> None:
        await self.accept()

    async def disconnect(self, close_code: int) -> None:
        self._conversation.clear()

    async def receive(
        self,
        text_data: str | None = None,
        bytes_data: bytes | None = None,
    ) -> None:
        if not text_data:
            return

        user_message = text_data.strip()
        if not user_message:
            return

        self._conversation.append({"role": "user", "content": user_message})

        try:
            async for token in stream_chat(self._conversation):
                await self.send(text_data=token)
        except LLMError as exc:
            await self.send(text_data=f'<div class="text-red-500 p-2">Error: {exc}</div>')
            self._conversation.pop()
