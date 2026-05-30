"""Root URL configuration."""

from django.urls import path

from chat.views import chat_page, health_check

urlpatterns = [
    path("", chat_page, name="chat"),
    path("health/", health_check, name="health"),
]
