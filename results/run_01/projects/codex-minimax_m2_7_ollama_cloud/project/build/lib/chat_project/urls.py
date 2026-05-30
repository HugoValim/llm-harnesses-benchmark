"""URL configuration for chat_project."""

from django.urls import include, path

urlpatterns = [
    path("", include("chat.urls")),
]
