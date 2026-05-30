from django.urls import path

from chat_app import views

urlpatterns = [
    path("", views.chat_page, name="chat"),
    path("health/", views.health, name="health"),
]
