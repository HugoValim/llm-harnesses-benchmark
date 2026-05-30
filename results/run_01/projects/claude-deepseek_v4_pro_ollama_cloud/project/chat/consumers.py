import json

from channels.generic.websocket import AsyncWebsocketConsumer

from .llm_service import LLMService


class ChatConsumer(AsyncWebsocketConsumer):  # type: ignore[misc]
    # channels package lacks type stubs
    """WebSocket consumer that streams LLM tokens to the browser."""

    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self.llm: LLMService = LLMService()
        self.history: list[dict[str, str]] = []

    async def connect(self) -> None:
        await self.accept()

    async def disconnect(self, close_code: int) -> None:
        pass

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        if text_data is None:
            return

        try:
            data = json.loads(text_data)
            message = data.get("message", "").strip()
            if not message:
                await self.send(text_data=json.dumps({"error": "Empty message"}))
                return
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({"error": "Invalid JSON"}))
            return

        self.history.append({"role": "user", "content": message})

        await self.send(text_data=json.dumps({"type": "stream_start"}))

        try:
            full_response = ""
            async for token in self.llm.stream(self.history):
                full_response += token
                await self.send(text_data=json.dumps({"type": "token", "content": token}))
        except Exception as exc:
            error_msg = f"LLM streaming failed: {exc}"
            await self.send(text_data=json.dumps({"type": "error", "content": error_msg}))
            return

        self.history.append({"role": "assistant", "content": full_response})
        await self.send(text_data=json.dumps({"type": "stream_end", "content": full_response}))
