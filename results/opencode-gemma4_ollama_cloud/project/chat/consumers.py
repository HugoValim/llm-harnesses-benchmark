import json

from channels.generic.websocket import AsyncWebsocketConsumer
from langchain_core.messages import AIMessage

from chat.services import LLMService


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.llm_service = LLMService()
        self.history = []  # (user_text, ai_msg_obj)
        await self.accept()

    async def disconnect(self, close_code):
        # Clean up resources
        del self.llm_service
        del self.history

    async def receive(self, text_data):
        data = json.loads(text_data)
        prompt = data.get("prompt", "")

        if not prompt:
            return

        # 1. Send user message fragment (handled by HTMX on client, but we can acknowledge)
        # HTMX ws-send usually just sends the data.
        # We send the AI responding indicator.
        await self.send(
            text_data=json.dumps(
                {
                    "type": "message",
                    "content": '<div id="chat-loading" class="text-gray-400 italic text-sm">AI is thinking...</div>',
                    "role": "ai",
                }
            )
        )

        full_response = ""

        # 2. Stream from LLM
        try:
            async for token in self.llm_service.stream_chat(prompt, self.history):
                full_response += token
                # We send partial updates. HTMX ws extension typically replaces or appends.
                # For streaming, we can use a specific ID and replace it, or just append tokens.
                # Since we want ChatGPT-style, we'll send a chunk that HTMX can append.
                await self.send(
                    text_data=json.dumps(
                        {"type": "token", "content": token, "role": "ai"}
                    )
                )

            # 3. Final AI message and update history
            await self.send(
                text_data=json.dumps({"type": "done", "content": "", "role": "ai"})
            )
            self.history.append((prompt, AIMessage(content=full_response)))

        except Exception as e:
            await self.send(
                text_data=json.dumps(
                    {"type": "error", "content": f"Error: {str(e)}", "role": "ai"}
                )
            )
