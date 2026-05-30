import httpx
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render


async def health(request):
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.OLLAMA_HOST}/api/tags")
        reachable = resp.status_code == 200
    except Exception:
        reachable = False
    return JsonResponse({"ollama_reachable": reachable, "model": settings.OLLAMA_MODEL})


def index(request):
    return render(request, "chat/index.html")
