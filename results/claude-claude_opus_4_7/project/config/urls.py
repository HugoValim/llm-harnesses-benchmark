"""Root URL configuration: admin plus the chat SPA routes."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("chat.urls")),
]
