import os
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
from typing import AsyncIterator

class OllamaService:
    def __init__(self, base_url: str = None, model: str = None):
        self.base_url = base_url or os.getenv('OLLAMA_HOST', 'http://localhost:11434')
        self.model = model or os.getenv('OLLAMA_MODEL', 'qwen2.5:7b')
        self.llm = ChatOllama(
            base_url=self.base_url,
            model=self.model
        )
    
    async def stream_response(self, messages: list) -> AsyncIterator[str]:
        """
        Stream response from Ollama model
        """
        try:
            async for chunk in self.llm.astream(messages):
                if chunk.content:
                    yield chunk.content
        except Exception as e:
            yield f"Error: {str(e)}"
    
    async def get_response(self, messages: list) -> str:
        """
        Get complete response from Ollama model
        """
        try:
            response = await self.llm.ainvoke(messages)
            return response.content
        except Exception as e:
            return f"Error: {str(e)}"
