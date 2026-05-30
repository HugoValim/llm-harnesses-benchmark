import os
from typing import AsyncGenerator

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_ollama import ChatOllama


class LLMService:
    def __init__(self) -> None:
        self.host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
        self.llm = ChatOllama(
            base_url=self.host,
            model=self.model,
        )

    async def stream_chat(self, messages: list[dict[str, str]]) -> AsyncGenerator[str, None]:
        """
        Streams a response from Ollama based on a list of messages.
        messages: list of {'role': 'user'|'assistant', 'content': '...'}
        """
        formatted_messages: list[BaseMessage] = []
        for msg in messages:
            if msg["role"] == "user":
                formatted_messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                formatted_messages.append(AIMessage(content=msg["content"]))

        try:
            async for chunk in self.llm.astream(formatted_messages):
                if chunk.content:
                    yield str(chunk.content)
        except Exception as e:
            yield f"Error: {str(e)}"
