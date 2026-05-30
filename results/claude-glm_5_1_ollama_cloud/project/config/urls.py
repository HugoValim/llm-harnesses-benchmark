from django.contrib import admin
from django.urls import path

from chat.views import chat_index, health_check

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health_check, name="health_check"),
    path("", chat_index, name="chat_index"),
]
