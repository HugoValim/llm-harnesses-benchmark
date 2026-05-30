"""Pytest configuration and shared fixtures."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key-for-pytest-32chars-xx")
os.environ.setdefault("OLLAMA_HOST", "http://localhost:11434")
os.environ.setdefault("OLLAMA_MODEL", "qwen2.5:7b")

import pytest
from django.test import Client
from langchain_core.messages import AIMessage, HumanMessage


@pytest.fixture
def client():
    """Django test client."""
    return Client()


@pytest.fixture
def fake_llm_chunks():
    """Return a sequence of LLM response chunks for mocking."""
    return ["Hello", " ", "world", "!"]


@pytest.fixture
def fake_messages():
    """Return a sequence of LangChain message objects for mocking."""
    return [
        HumanMessage(content="Hi"),
        AIMessage(content="Hello there!"),
    ]
