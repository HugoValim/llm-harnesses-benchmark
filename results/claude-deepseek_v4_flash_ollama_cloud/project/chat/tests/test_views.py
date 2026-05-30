from django.test import TestCase


class IndexViewTest(TestCase):
    def test_renders_200(self):
        response = self.client.get('/')
        assert response.status_code == 200

    def test_uses_correct_template(self):
        response = self.client.get('/')
        self.assertTemplateUsed(response, 'chat/index.html')

    def test_contains_chat_form(self):
        response = self.client.get('/')
        self.assertContains(response, 'id="chat-form"')

    def test_contains_message_area(self):
        response = self.client.get('/')
        self.assertContains(response, 'id="messages"')
