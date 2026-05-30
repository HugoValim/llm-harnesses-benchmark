from django.urls import path

from chat.views import chat_view, health_view

urlpatterns = [
    path("", chat_view, name="chat"),
    path("health/", health_view, name="health"),
]
