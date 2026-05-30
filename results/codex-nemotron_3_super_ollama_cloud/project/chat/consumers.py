import json
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils.html import escape
from .services.ollama_service import get_ollama_model


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        # Send a welcome message
        await self.send(
            text_data=json.dumps(
                {"type": "system", "message": "Connected to the chat service."}
            )
        )

    async def disconnect(self, close_code):
        pass

    async def receive(self, text_data):
        # The incoming data is the plain string from the input (value)
        user_message = text_data.strip()
        if not user_message:
            return

        # Escape the user message for HTML
        escaped_user = escape(user_message)
        # Send the user's message back as a chat bubble (from user)
        user_html = f'<div class="message message-user bg-blue-500 text-white px-3 py-2 rounded-xl max-w-[80%] self-end">{escaped_user}</div>'
        await self.send(text_data=json.dumps({"type": "chunk", "html": user_html}))

        # Get the Ollama model instance
        ollama_model = get_ollama_model()

        # Stream the response from Ollama
        try:
            async for chunk in ollama_model.astream(user_message):
                if hasattr(chunk, "content"):
                    content = chunk.content
                elif isinstance(chunk, str):
                    content = chunk
                else:
                    content = str(chunk)

                # Escape the AI content
                escaped_content = escape(content)
                ai_html = f'<div class="message message-assistant bg-gray-200 text-gray-900 px-3 py-2 rounded-xl max-w-[80%] self-start">{escaped_content}</div>'
                await self.send(
                    text_data=json.dumps({"type": "chunk", "html": ai_html})
                )
        except Exception as e:
            error_msg = f"An error occurred: {str(e)}"
            escaped_error = escape(error_msg)
            error_html = f'<div class="message message-error bg-red-500 text-white px-3 py-2 rounded-xl max-w-[80%] self-start">{escaped_error}</div>'
            await self.send(text_data=json.dumps({"type": "chunk", "html": error_html}))
