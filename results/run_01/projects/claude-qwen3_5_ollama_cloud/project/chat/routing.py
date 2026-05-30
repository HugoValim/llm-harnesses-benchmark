"""
WebSocket URL routing for chat consumers.
"""

from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path("ws/chat/", consumers.ChatConsumer.as_asgi(), name="websocket_chat"),  # type: ignore[arg-type]
]
