import os
from langchain_ollama import ChatOllama


def get_ollama_model():
    """
    Returns a ChatOllama instance configured with environment variables.
    OLLAMA_HOST defaults to http://localhost:11434
    OLLAMA_MODEL defaults to qwen2.5:7b
    """
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
    return ChatOllama(model=model, base_url=host)
