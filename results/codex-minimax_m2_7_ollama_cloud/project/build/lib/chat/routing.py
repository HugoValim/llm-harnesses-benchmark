"""WebSocket URL routing for chat app."""

from django.urls import re_path

from chat.consumers import ChatConsumer

websocket_urlpatterns = [
    re_path(r"ws/chat/$", ChatConsumer.as_asgi()),  # type: ignore[arg-type]
]
