"""pytest configuration."""

import os

import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ollama_chat.test_settings")
os.environ.setdefault("OLLAMA_HOST", "http://localhost:11434")
os.environ.setdefault("OLLAMA_MODEL", "qwen2.5:7b")


@pytest.fixture
def fake_chat_chunk():
    """Yield a sequence of fake streamed chunks."""

    class FakeChunk:
        def __init__(self, content: str) -> None:
            self.content = content

    return [FakeChunk("Hello, "), FakeChunk("world!"), FakeChunk(" How can I help?")]
