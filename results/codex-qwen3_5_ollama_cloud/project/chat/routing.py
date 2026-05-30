"""
WebSocket routing for chat.
"""

from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path("ws/chat/", consumers.ChatConsumer.as_asgi(), name="websocket_chat"),
]
