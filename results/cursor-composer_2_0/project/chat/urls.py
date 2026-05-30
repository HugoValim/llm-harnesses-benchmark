from __future__ import annotations

from django.urls import path

from chat import views

urlpatterns = [
    path("", views.chat_spa, name="chat-spa"),
    path("health/", views.health, name="health"),
    path("health/live/", views.health_live, name="health-live"),
]
