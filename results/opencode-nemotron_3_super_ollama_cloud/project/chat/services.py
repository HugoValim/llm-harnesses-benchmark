import os
from langchain_ollama import ChatOllama


class OllamaService:
    def __init__(self):
        self.model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
        self.base_url = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.llm = ChatOllama(model=self.model, base_url=self.base_url)

    async def stream_response(self, messages):
        """
        Stream response from Ollama model

        Args:
            messages: List of message dictionaries with 'role' and 'content'

        Yields:
            str: Content chunks from the model response
        """
        try:
            # Convert messages to format expected by LangChain
            lc_messages = []
            for msg in messages:
                if msg["role"] == "system":
                    lc_messages.append(("system", msg["content"]))
                elif msg["role"] == "user":
                    lc_messages.append(("human", msg["content"]))
                elif msg["role"] == "assistant":
                    lc_messages.append(("ai", msg["content"]))

            # Stream the response
            async for chunk in self.llm.astream(lc_messages):
                if hasattr(chunk, "content"):
                    yield chunk.content
                else:
                    yield str(chunk)
        except Exception as e:
            yield f"Error: {str(e)}"
