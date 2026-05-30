import pytest
from django.test import RequestFactory

from chat.views import health_check, index


@pytest.mark.asyncio
async def test_index_view():
    rf = RequestFactory()
    request = rf.get('/')
    response = await index(request)
    assert response.status_code == 200
    assert b"Ollama Chat" in response.content

@pytest.mark.asyncio
async def test_health_view():
    rf = RequestFactory()
    request = rf.get('/health/')
    response = await health_check(request)
    assert response.status_code == 200
    # It might be Online or Offline depending on environment
    assert b"Ollama Health" in response.content
