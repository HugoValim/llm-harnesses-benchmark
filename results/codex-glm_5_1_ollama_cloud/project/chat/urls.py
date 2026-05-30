"""URL configuration for the chat app."""

from django.urls import path

from chat.views import HealthView, IndexView

urlpatterns = [
    path("", IndexView.as_view(), name="index"),
    path("health/", HealthView.as_view(), name="health"),
]
