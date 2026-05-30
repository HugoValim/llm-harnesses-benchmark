import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

from chat.services import stream_reply

logger = logging.getLogger(__name__)


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self) -> None:
        session = self.scope.get("session")
        self.session_id = str(session.session_key if session else id(self))
        self.group_name = f"chat_{self.session_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        self.history: list[dict[str, str]] = []
        self._streaming = False

    async def disconnect(self, close_code: int) -> None:
        self._streaming = False
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data: str) -> None:
        data = json.loads(text_data)
        message = data.get("message", "").strip()
        if not message:
            return
        self.history.append({"role": "human", "content": message})
        await self.send(
            text_data=json.dumps(
                {
                    "type": "user_message",
                    "content": message,
                }
            )
        )
        await self.send(
            text_data=json.dumps(
                {
                    "type": "bot_start",
                }
            )
        )
        self._streaming = True
        reply_parts: list[str] = []
        try:
            async for chunk in stream_reply(self.history):
                if not self._streaming:
                    break
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "bot_token",
                            "content": chunk,
                        }
                    )
                )
                reply_parts.append(chunk)
        except Exception as exc:
            logger.exception("consumer stream error")
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "bot_error",
                        "content": str(exc),
                    }
                )
            )
        finally:
            self._streaming = False
            reply = "".join(reply_parts)
            if reply:
                self.history.append({"role": "ai", "content": reply})
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "bot_end",
                    }
                )
            )
