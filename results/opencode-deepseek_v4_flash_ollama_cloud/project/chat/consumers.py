import json
import logging
from collections.abc import AsyncIterable

from channels.generic.websocket import AsyncWebsocketConsumer

from chat.llm_service import create_llm

logger = logging.getLogger(__name__)


class ChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._messages: list[dict[str, str]] = []

    async def connect(self) -> None:
        await self.accept()

    async def disconnect(self, close_code: int) -> None:
        self._messages.clear()

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        if bytes_data is not None:
            text_data = bytes_data.decode('utf-8')
        if text_data is None:
            return

        data = json.loads(text_data)
        user_message = data.get('message', '')
        if not user_message:
            return

        self._messages.append({'role': 'user', 'content': user_message})

        try:
            llm = create_llm()
            full_response = ''
            async for chunk in self._stream_chunks(llm):
                full_response += chunk
                await self.send(
                    text_data=json.dumps(
                        {
                            'type': 'token',
                            'content': chunk,
                        }
                    )
                )

            self._messages.append({'role': 'assistant', 'content': full_response})
            await self.send(
                text_data=json.dumps(
                    {
                        'type': 'done',
                        'content': '',
                    }
                )
            )
        except Exception as e:
            logger.exception('LLM streaming failed')
            await self.send(
                text_data=json.dumps(
                    {
                        'type': 'error',
                        'content': f'Failed to get response from Ollama: {e}',
                    }
                )
            )

    async def _stream_chunks(self, llm) -> AsyncIterable[str]:
        async for chunk in llm.astream(self._messages):
            content = getattr(chunk, 'content', '')
            if content:
                yield content
