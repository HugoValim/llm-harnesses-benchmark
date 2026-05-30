from django.shortcuts import render


def index(request):
    return render(request, "chat/index.html")


def health_check(request):
    from chat.services import LLMService

    try:
        # Simple check if LLM service is configured and reachability can be tested
        # Since ChatOllama doesn't have a simple 'ping', we just check if it's init-able
        # In a real app, we might do a small request.
        LLMService()
        return render(request, "chat/health.html", {"status": "Ollama configured"})
    except Exception as e:
        return render(
            request,
            "chat/health.html",
            {"status": f"Ollama error: {str(e)}"},
            status=500,
        )
