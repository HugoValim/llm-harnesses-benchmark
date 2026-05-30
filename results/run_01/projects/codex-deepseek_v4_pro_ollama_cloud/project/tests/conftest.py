"""Shared test fixtures and configuration."""

import pytest


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch):
    """Ensure tests never depend on real secrets or external config."""
    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-secret-key-for-tests-only")
    monkeypatch.setenv("OLLAMA_HOST", "http://fake-ollama:9999")
    monkeypatch.setenv("OLLAMA_MODEL", "fake-model")
    monkeypatch.setenv("DJANGO_DEBUG", "True")
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
