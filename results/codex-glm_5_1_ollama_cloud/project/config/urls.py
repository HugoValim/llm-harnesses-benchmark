"""Root URL configuration — delegates to the chat app."""

from django.urls import include, path

urlpatterns = [
    path("", include("chat.urls")),
]
