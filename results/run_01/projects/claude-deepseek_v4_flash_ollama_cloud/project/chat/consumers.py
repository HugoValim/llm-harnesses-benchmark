import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

from .services.llm import ChatService

logger = logging.getLogger(__name__)


class ChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.chat_service = ChatService()
        self.messages: list[dict] = []

    async def connect(self):
        await self.accept()

    async def disconnect(self, code):
        pass

    async def receive(self, text_data):
        data = json.loads(text_data)
        user_message = data.get('message', '').strip()
        if not user_message:
            return

        self.messages.append({'role': 'user', 'content': user_message})

        await self.send(
            text_data=json.dumps(
                {
                    'type': 'user-message',
                    'message': user_message,
                }
            )
        )

        await self.send(
            text_data=json.dumps(
                {
                    'type': 'info',
                    'message': 'Waiting for model response...',
                }
            )
        )

        full_response = ''
        try:
            async for chunk in self.chat_service.stream(self.messages):
                if chunk:
                    full_response += chunk
                    await self.send(
                        text_data=json.dumps(
                            {
                                'type': 'chunk',
                                'content': chunk,
                            }
                        )
                    )
        except Exception as e:
            logger.exception('Ollama streaming failed')
            await self.send(
                text_data=json.dumps(
                    {
                        'type': 'error',
                        'message': f'Ollama connection failed: {e}',
                    }
                )
            )
            return

        self.messages.append({'role': 'assistant', 'content': full_response})

        await self.send(
            text_data=json.dumps(
                {
                    'type': 'done',
                }
            )
        )
