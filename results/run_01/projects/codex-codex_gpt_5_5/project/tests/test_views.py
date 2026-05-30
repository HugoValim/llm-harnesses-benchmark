from http import HTTPStatus
from typing import Self

import pytest
from django.template.loader import render_to_string
from django.test import Client


class FakeOllamaResponse:
    status = HTTPStatus.OK

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> bool:
        return False


class FakeUrlOpen:
    def __init__(self) -> None:
        self.timeout: float | None = None

    def __call__(self, request: object, timeout: float) -> FakeOllamaResponse:
        self.timeout = timeout
        return FakeOllamaResponse()


def test_index_renders_spa_websocket_wiring(client: Client) -> None:
    response = client.get("/")

    assert response.status_code == HTTPStatus.OK
    html = response.content.decode()
    assert 'hx-ext="ws"' in html
    assert 'ws-connect="/ws/chat/"' in html
    assert "ws-send" in html
    assert "https://unpkg.com/htmx.org@2.0.10/dist/htmx.min.js" in html
    assert "https://unpkg.com/htmx-ext-ws@2.0.4/ws.js" in html


def test_message_partial_renders_assistant_target() -> None:
    html = render_to_string(
        "chat/partials/message.html",
        {"message_id": "msg-test", "role": "assistant", "content": "Hello"},
    )

    assert 'id="assistant-content-msg-test"' in html
    assert "Hello" in html


@pytest.mark.django_db
def test_ollama_health_reports_reachable(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_urlopen = FakeUrlOpen()
    monkeypatch.setattr("chat.views.urlopen", fake_urlopen)

    response = client.get("/health/ollama/")

    assert response.status_code == HTTPStatus.OK
    assert response.json()["status"] == "reachable"
    assert response.json()["model"] == "qwen2.5:7b"
    assert fake_urlopen.timeout == 2.0
