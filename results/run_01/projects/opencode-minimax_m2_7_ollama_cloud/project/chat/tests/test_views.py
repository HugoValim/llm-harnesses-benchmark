from unittest.mock import patch

import pytest
from django.test import Client


@pytest.mark.django_db
def test_chat_view_renders() -> None:
    client = Client()
    with patch("chat.views.get_ollama_service") as mock_service:
        mock_service.return_value = type(
            "MockService",
            (),
            {
                "_host": "http://localhost:11434",
                "_model": "qwen2.5:7b",
            },
        )()

        response = client.get("/chat/")

        assert response.status_code == 200
        assert "htmx" in response.content.decode().lower()
        assert "ws-connect" in response.content.decode()


@pytest.mark.django_db
def test_chat_view_contains_ollama_config() -> None:
    client = Client()
    with patch("chat.views.get_ollama_service") as mock_service:
        mock_instance = type(
            "MockService",
            (),
            {
                "_host": "http://custom:11434",
                "_model": "custom-model",
            },
        )()
        mock_service.return_value = mock_instance

        response = client.get("/chat/")

        content = response.content.decode()
        assert "ws-connect" in content


@pytest.mark.django_db
def test_health_view_returns_config() -> None:
    client = Client()
    with patch("chat.views.get_ollama_service") as mock_service:
        mock_instance = type(
            "MockService",
            (),
            {
                "_host": "http://test:11434",
                "_model": "test-model",
                "check_health": lambda: {"status": "ok"},
            },
        )()
        mock_service.return_value = mock_instance

        response = client.get("/health/")

        assert response.status_code == 200
        data = response.json()
        assert data["ollama_host"] == "http://test:11434"
        assert data["ollama_model"] == "test-model"
