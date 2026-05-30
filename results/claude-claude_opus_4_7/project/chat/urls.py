"""HTTP URL routes for the chat app."""

from __future__ import annotations

from django.urls import path

from chat import views

app_name = "chat"

urlpatterns = [
    path("", views.index, name="index"),
    path("health/", views.health, name="health"),
]
