"""
URL patterns for chat app.
"""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.chat_view, name="chat"),
    path("health/", views.health_check_view, name="health_check"),
]
