from django.shortcuts import render

from .services.llm import ChatService


async def index(request):
    """Renders the main chat UI."""
    return render(request, 'chat/index.html')

async def health_check(request):
    """Reports Ollama reachability."""
    service = ChatService()
    is_healthy = await service.check_health()
    return render(request, 'chat/health.html', {'healthy': is_healthy})
