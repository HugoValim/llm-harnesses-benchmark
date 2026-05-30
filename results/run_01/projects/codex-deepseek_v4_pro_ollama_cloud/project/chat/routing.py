"""WebSocket routing for the chat app."""

from django.urls import path

from chat.consumers import ChatConsumer

websocket_urlpatterns = [
    path("ws/chat/", ChatConsumer.as_asgi(), name="ws_chat"),
]
