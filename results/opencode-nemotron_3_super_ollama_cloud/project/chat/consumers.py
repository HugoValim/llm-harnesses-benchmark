import json
from channels.generic.websocket import AsyncWebsocketConsumer
from .services import OllamaService


class ChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ollama_service = OllamaService()
        self.chat_history = []

    async def connect(self):
        await self.accept()
        # Initialize with a system message
        self.chat_history = [
            {"role": "system", "content": "You are a helpful assistant."}
        ]

    async def disconnect(self, close_code):
        # Clean up resources if needed
        self.chat_history.clear()

    async def receive(self, text_data):
        try:
            text_data_json = json.loads(text_data)
            message = text_data_json.get("message", "").strip()

            if not message:
                return

            # Add user message to history
            self.chat_history.append({"role": "user", "content": message})

            # Send user message back to client for immediate display
            await self.send(
                text_data=json.dumps({"type": "user_message", "message": message})
            )

            # Stream response from Ollama
            full_response = ""
            async for chunk in self.ollama_service.stream_response(self.chat_history):
                full_response += chunk
                # Send each chunk to the client
                await self.send(
                    text_data=json.dumps({"type": "assistant_chunk", "chunk": chunk})
                )

            # Add complete assistant response to history
            self.chat_history.append({"role": "assistant", "content": full_response})

            # Signal end of streaming
            await self.send(
                text_data=json.dumps(
                    {"type": "assistant_complete", "message": full_response}
                )
            )

        except json.JSONDecodeError:
            await self.send(
                text_data=json.dumps(
                    {"type": "error", "message": "Invalid JSON received"}
                )
            )
        except Exception as e:
            await self.send(
                text_data=json.dumps(
                    {"type": "error", "message": f"Server error: {str(e)}"}
                )
            )
