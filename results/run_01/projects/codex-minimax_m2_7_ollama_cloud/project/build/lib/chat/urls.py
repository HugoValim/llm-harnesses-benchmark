"""URL routing for chat app."""

from django.urls import path

from chat.views import health_check, home

urlpatterns = [
    path("", home, name="home"),
    path("health/", health_check, name="health_check"),
]
