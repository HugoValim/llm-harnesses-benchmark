import json

from channels.generic.websocket import AsyncWebsocketConsumer
from langchain_core.messages import AIMessage, HumanMessage

from .services.llm import ChatService


class ChatConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time chat streaming.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.llm_service = ChatService()
        self.history = []

    async def connect(self) -> None:
        await self.accept()

    async def disconnect(self, close_code: int) -> None:
        """Clean up resources on disconnect."""
        self.history = []
        await self.close(close_code)

    async def receive(self, text_data: str) -> None:
        # Expected format from HTMX ws-send: a simple string or JSON
        try:
            data = json.loads(text_data)
            user_input = data.get('message', '')
        except json.JSONDecodeError:
            user_input = text_data

        if not user_input:
            return

        # 1. Send user message back immediately (echo for UI)
        await self.send(text_data=self._render_message("user", user_input))

        # 2. Stream AI response
        ai_msg_id = "ai-response-current"
        await self.send(text_data=self._render_message("ai", "", msg_id=ai_msg_id))

        full_response = ""
        async for token in self.llm_service.stream_chat(self.history, user_input):
            full_response += token
            await self.send(text_data=self._render_message("ai", full_response, msg_id=ai_msg_id))

        # 3. Update history for next turn
        self.history.append(HumanMessage(content=user_input))
        self.history.append(AIMessage(content=full_response))

    def _render_message(self, role: str, content: str, msg_id: str = None) -> str:
        """
        Renders a simple HTML fragment for HTMX.
        """
        id_attr = f'id="{msg_id}"' if msg_id else ""
        cls = "bg-blue-100 text-blue-800" if role == "user" else "bg-gray-100 text-gray-800"
        align = "text-right" if role == "user" else "text-left"
        
        return f'<div {id_attr} class="p-2 m-2 rounded-lg {cls} {align} max-w-xs ml-auto" hx-swap-oob="innerHTML">{content}</div>'
