"""HTTP routes for the chat UI and health checks."""

from django.urls import path

from chat import views

urlpatterns = [
    path("", views.chat_index, name="chat_index"),
    path("health/ollama/", views.ollama_health, name="ollama_health"),
]
