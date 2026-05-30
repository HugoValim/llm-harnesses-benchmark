from django.urls import path

from chat.views import index, ollama_health

urlpatterns = [
    path("", index, name="chat-index"),
    path("health/ollama/", ollama_health, name="ollama-health"),
]
