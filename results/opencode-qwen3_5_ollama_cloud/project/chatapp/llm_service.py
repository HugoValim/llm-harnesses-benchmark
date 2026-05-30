"""
LLM service module for ChatOllama integration.
"""

import os

from langchain_ollama import ChatOllama


def get_chat_model() -> ChatOllama:
    """Create and return a ChatOllama instance from environment config."""
    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    ollama_model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")

    return ChatOllama(
        model=ollama_model,
        base_url=ollama_host,
    )
