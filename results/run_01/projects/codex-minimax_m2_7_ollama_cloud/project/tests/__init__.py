"""Test environment: set before pytest-django loads Django settings."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key-for-pytest-32chars-xx")
os.environ.setdefault("OLLAMA_HOST", "http://localhost:11434")
os.environ.setdefault("OLLAMA_MODEL", "qwen2.5:7b")
