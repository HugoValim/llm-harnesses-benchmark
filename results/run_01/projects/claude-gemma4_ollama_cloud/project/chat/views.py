from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def chat_view(request: HttpRequest) -> HttpResponse:
    return render(request, "chat/index.html")
