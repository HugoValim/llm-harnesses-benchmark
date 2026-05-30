import json
from typing import Any

from channels.generic.websocket import AsyncWebsocketConsumer

from .services import LLMService


class ChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.llm_service = LLMService()
        self.chat_history: list[dict[str, str]] = []
        self.current_response_id: str | None = None

    async def connect(self) -> None:
        await self.accept()

    async def disconnect(self, close_code: int) -> None:
        self.chat_history = []
        self.current_response_id = None

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        if text_data is None:
            return

        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        user_message = data.get("message", "")
        if not user_message:
            return

        self.chat_history.append({"role": "user", "content": user_message})

        user_html = f"""
        <div id="messages" hx-swap-oob="beforeend">
            <div class="bg-blue-600 p-3 rounded-lg max-w-xs self-end ml-auto text-right">
                {user_message}
            </div>
        </div>
        """
        await self.send(text_data=user_html)

        self.current_response_id = f"resp-{len(self.chat_history)}"
        assistant_start_html = f"""<div id="messages" hx-swap-oob="beforeend">
                <div id="{self.current_response_id}"
                     class="bg-gray-800 p-3 rounded-lg max-w-xs self-start">
                    <span class="opacity-50">...</span>
                </div>
            </div>"""
        await self.send(text_data=assistant_start_html)

        full_response = ""
        try:
            async for chunk in self.llm_service.stream_chat(self.chat_history):
                full_response += chunk
                if full_response == chunk:
                    chunk_html = f"""
                    <div id="{self.current_response_id}" hx-swap-oob="innerHTML">
                        {chunk}
                    </div>
                    """
                else:
                    chunk_html = f"""
                    <div id="{self.current_response_id}" hx-swap-oob="beforeend">
                        {chunk}
                    </div>
                    """
                await self.send(text_data=chunk_html)

        except Exception as e:
            error_html = f"""
            <div id="messages" hx-swap-oob="beforeend">
                <div class="bg-red-900 p-3 rounded-lg max-w-xs self-start text-red-200">
                    Error: {str(e)}
                </div>
            </div>
            """
            await self.send(text_data=error_html)

        self.chat_history.append({"role": "assistant", "content": full_response})
        self.current_response_id = None
