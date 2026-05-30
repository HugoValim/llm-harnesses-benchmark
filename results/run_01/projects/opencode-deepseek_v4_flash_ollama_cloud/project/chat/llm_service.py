import os

from langchain_ollama import ChatOllama

OLLAMA_HOST = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'qwen2.5:7b')


def create_llm() -> ChatOllama:
    return ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_HOST,
    )


def check_ollama_reachable() -> bool:
    try:
        llm = create_llm()
        llm.invoke('ping')
        return True
    except Exception:
        return False
