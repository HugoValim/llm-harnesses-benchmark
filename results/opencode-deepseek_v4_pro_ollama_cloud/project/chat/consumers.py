import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

from .services import stream_response

logger = logging.getLogger(__name__)


class ChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.history: list[dict[str, str]] = []
        self.stream_task: object = None

    async def connect(self) -> None:
        await self.accept()
        await self.send(
            text_data=json.dumps({"type": "system", "content": "Connected. Ask me anything."})
        )

    async def disconnect(self, close_code: int) -> None:
        self.history.clear()
        self.stream_task = None

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        if not text_data:
            await self._send_error("No message data received.")
            return
        try:
            data = json.loads(text_data)
            user_message = data.get("message", "").strip()
            if not user_message:
                await self._send_error("Empty message.")
                return
        except (json.JSONDecodeError, TypeError) as exc:
            await self._send_error(f"Invalid message format: {exc}")
            return

        self.history.append({"role": "user", "content": user_message})

        await self.send(text_data=json.dumps({"type": "user", "content": user_message}))

        assistant_full = ""
        try:
            async for token in stream_response(list(self.history)):
                assistant_full += token
                await self.send(text_data=json.dumps({"type": "assistant_token", "content": token}))
        except Exception as exc:
            logger.exception("Streaming failed")
            self.history.pop()
            await self._send_error(f"Ollama request failed: {exc}")
            return

        await self.send(text_data=json.dumps({"type": "assistant_done", "content": ""}))

        if assistant_full:
            self.history.append({"role": "assistant", "content": assistant_full})

    async def _send_error(self, message: str) -> None:
        await self.send(text_data=json.dumps({"type": "error", "content": message}))
