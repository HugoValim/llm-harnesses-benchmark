from django.conf import settings
from langchain_ollama import ChatOllama


class ChatService:
    def __init__(self):
        self.llm = ChatOllama(
            model=settings.OLLAMA_MODEL,
            base_url=settings.OLLAMA_HOST,
        )

    async def stream(self, messages):
        langchain_messages = [(m['role'], m['content']) for m in messages]
        async for chunk in self.llm.astream(langchain_messages):
            content = chunk.content
            if content:
                yield content
