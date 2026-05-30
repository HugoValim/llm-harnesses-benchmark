from django.conf import settings
from django.shortcuts import render


def index(request):
    return render(
        request,
        'chat/index.html',
        {
            'ollama_model': settings.OLLAMA_MODEL,
        },
    )
