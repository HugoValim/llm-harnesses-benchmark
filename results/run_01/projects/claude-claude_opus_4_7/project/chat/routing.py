"""WebSocket URL routing for the chat app."""

from __future__ import annotations

from django.urls import path

from chat.consumers import ChatConsumer

websocket_urlpatterns = [
    path("ws/chat/", ChatConsumer.as_asgi()),
]
