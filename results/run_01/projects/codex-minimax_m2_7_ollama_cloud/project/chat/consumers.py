"""WebSocket consumer for streaming chat."""

import json
from typing import Any

from channels.generic.websocket import AsyncWebsocketConsumer

from chat.services.llm import ChatService, OllamaConnectionError


class ChatConsumer(AsyncWebsocketConsumer):
    """Streams LLM tokens to the browser via HTMX WebSocket extension."""

    _sessions: dict[str, ChatService] = {}

    async def connect(self) -> None:
        session_data: dict[str, Any] = self.scope.get("session", {})
        self.session_id: str = session_data.get("session_key") or "anon"
        self.group_name = f"chat_{self.session_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        self._sessions[self.session_id] = ChatService()

    async def disconnect(self, close_code: int) -> None:
        if self.session_id in self._sessions:
            del self._sessions[self.session_id]
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def _send_error(self, message: str) -> None:
        """Send a typed error response."""
        await self.send(text_data=json.dumps({"type": "error", "error": message}))

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        if not text_data:
            return

        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self._send_error("Invalid JSON")
            return

        action = data.get("action")

        if action == "reset":
            self._sessions[self.session_id].reset_history()
            await self.send(text_data=json.dumps({"type": "reset", "done": True}))
            return

        if action != "chat":
            await self._send_error(f"Unknown action: {action}")
            return

        prompt = data.get("prompt", "").strip()
        if not prompt:
            await self._send_error("Empty prompt")
            return

        await self.send(text_data=json.dumps({"type": "start"}))
        service = self._sessions.get(self.session_id)
        if not service:
            service = ChatService()
            self._sessions[self.session_id] = service

        full_response = ""
        try:
            async for token in service.astream_tokens(prompt):
                full_response += token
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "token",
                            "content": token,
                        }
                    )
                )
        except OllamaConnectionError as e:
            await self._send_error(str(e))
        except Exception as e:
            await self._send_error(f"Unexpected error: {e}")
        finally:
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "done",
                        "content": full_response,
                    }
                )
            )

    async def chat_message(self, event: dict[str, Any]) -> None:
        """Handle messages broadcast to the group."""
        await self.send(text_data=json.dumps(event))
