from django.contrib import admin
from django.urls import path

from chat.views import health_check, index

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", index, name="index"),
    path("health/", health_check, name="health_check"),
]
