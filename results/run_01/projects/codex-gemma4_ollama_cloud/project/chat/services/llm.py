import os
from typing import AsyncGenerator, List

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_ollama import ChatOllama


class ChatService:
    """Service for interfacing with Ollama via LangChain."""
    
    def __init__(self) -> None:
        self.host = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
        self.model = os.environ.get('OLLAMA_MODEL', 'qwen2.5:7b')
        self.client = ChatOllama(
            base_url=self.host,
            model=self.model,
        )

    async def stream_chat(self, history: List[BaseMessage], user_input: str) -> AsyncGenerator[str, None]:
        """
        Streams response from Ollama given conversation history.
        """
        messages = history + [HumanMessage(content=user_input)]
        
        try:
            async for chunk in self.client.astream(messages):
                if hasattr(chunk, 'content'):
                    yield chunk.content
                elif isinstance(chunk, str):
                    yield chunk
                else:
                    yield str(chunk)
        except Exception as e:
            yield f"\n[Error]: {str(e)}"

    async def check_health(self) -> bool:
        """Checks if Ollama is reachable."""
        try:
            await self.client.ainvoke("hi")
            return True
        except Exception:
            return False
