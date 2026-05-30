import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_chat_view_renders() -> None:
    from django.test import RequestFactory

    from chat.views import chat_view

    rf = RequestFactory()
    request = rf.get(reverse("chat"))
    response = chat_view(request)

    assert response.status_code == 200
    assert "Welcome!" in response.content.decode()
