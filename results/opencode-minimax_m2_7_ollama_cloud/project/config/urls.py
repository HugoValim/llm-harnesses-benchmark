from django.contrib import admin
from django.urls import path

from chat.views import chat_view, health_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("chat/", chat_view, name="chat"),
    path("health/", health_view, name="health"),
]
