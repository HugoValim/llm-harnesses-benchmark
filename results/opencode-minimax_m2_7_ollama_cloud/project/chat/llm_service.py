import os
from typing import Any

from langchain_ollama import ChatOllama


class OllamaService:
    _instance: "OllamaService | None" = None

    def __init__(self, host: str, model: str) -> None:
        self._host = host
        self._model = model
        self._llm = ChatOllama(
            model=model,
            base_url=host,
        )

    async def astream(self, messages: list[dict[str, Any]]) -> Any:
        async for chunk in self._llm.astream(messages):
            if chunk.content:
                yield chunk.content

    def check_health(self) -> dict[str, Any]:
        return {
            "host": self._host,
            "model": self._model,
            "status": "configured",
        }


def get_ollama_service() -> OllamaService:
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
    if OllamaService._instance is None:
        OllamaService._instance = OllamaService(host, model)
    return OllamaService._instance
