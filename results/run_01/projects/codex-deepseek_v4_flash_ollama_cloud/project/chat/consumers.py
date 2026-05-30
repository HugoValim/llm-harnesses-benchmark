import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

from chat.llm_service import stream_response

logger = logging.getLogger(__name__)


class ChatConsumer(AsyncWebsocketConsumer):  # type: ignore[misc]
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._conversation_history: list[dict[str, str]] = []
        self._streaming: bool = False

    async def connect(self) -> None:
        await self.accept()
        logger.info("WebSocket connected: %s", self.channel_name)

    async def disconnect(self, close_code: int) -> None:
        self._streaming = False
        self._conversation_history.clear()
        logger.info(
            "WebSocket disconnected: %s code=%s",
            self.channel_name,
            close_code,
        )

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        if self._streaming:
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "content": "A response is already being generated.",
                    }
                )
            )
            return

        data = json.loads(text_data or "{}")
        message = data.get("message", "").strip()
        if not message:
            return

        self._conversation_history.append({"role": "user", "content": message})
        self._streaming = True

        full_content = ""
        try:
            async for chunk in stream_response(self._conversation_history):
                full_content += chunk
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "chunk",
                            "content": chunk,
                        }
                    )
                )

            self._conversation_history.append(
                {
                    "role": "assistant",
                    "content": full_content,
                }
            )
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "done",
                        "content": "",
                    }
                )
            )
        except Exception:
            logger.exception("Streaming failed")
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "content": "Streaming failed. Check Ollama connection.",
                    }
                )
            )
        finally:
            self._streaming = False
