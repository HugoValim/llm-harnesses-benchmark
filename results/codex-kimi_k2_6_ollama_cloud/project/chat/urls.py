from django.urls import path

from chat import consumers, views

urlpatterns = [
    path("", views.index, name="index"),
    path("health/", views.health, name="health"),
]

websocket_urlpatterns = [
    path("ws/chat/", consumers.ChatConsumer.as_asgi()),
]
