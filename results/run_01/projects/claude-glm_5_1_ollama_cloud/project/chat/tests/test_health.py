from __future__ import annotations

import pytest
from django.test import RequestFactory

from chat.views import health_check


@pytest.mark.django_db
def test_health_check_returns_json():
    factory = RequestFactory()
    request = factory.get("/health/")
    response = health_check(request)
    assert response.status_code == 200
    import json

    data = json.loads(response.content)
    assert "status" in data
    assert "ollama_reachable" in data
