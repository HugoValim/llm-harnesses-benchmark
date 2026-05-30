import os

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama


class LLMService:
    def __init__(self):
        self.model_name = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
        self.base_url = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.llm = ChatOllama(
            model=self.model_name, base_url=self.base_url, streaming=True
        )

    async def stream_chat(self, prompt, history):
        messages = [SystemMessage(content="You are a helpful AI assistant.")]
        for user_msg, ai_msg in history:
            messages.append(HumanMessage(content=user_msg))
            messages.append(ai_msg)  # ai_msg is already a Message object

        messages.append(HumanMessage(content=prompt))

        try:
            async for chunk in self.llm.astream(messages):
                yield chunk.content
        except Exception as e:
            yield f"Error: Could not connect to Ollama at {self.base_url}. {str(e)}"
