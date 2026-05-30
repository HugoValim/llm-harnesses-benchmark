from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from chat.services import ollama_reachable


def index(request: HttpRequest) -> HttpResponse:
    return render(request, "chat/index.html")


def health(request: HttpRequest) -> JsonResponse:
    reachable = ollama_reachable()
    return JsonResponse({"ollama_reachable": reachable})
