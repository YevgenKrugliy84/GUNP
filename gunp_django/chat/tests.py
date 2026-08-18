import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import PrivateChatMessage, PublicChatMessage

User = get_user_model()


class PublicChatTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='chatter', password='pass12345')
        self.client.force_login(self.user)

    def test_send_and_list_public_message(self):
        response = self.client.post(
            reverse('chat:send'),
            data=json.dumps({'chat_type': 'public', 'message': 'Привіт усім'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(PublicChatMessage.objects.filter(message='Привіт усім').exists())

        response = self.client.get(reverse('chat:messages'), {'type': 'public', 'since': 0})
        data = response.json()
        self.assertEqual(len(data['messages']), 1)
        self.assertEqual(data['messages'][0]['message'], 'Привіт усім')


class PrivateChatThreadTests(TestCase):
    def setUp(self):
        self.regular_user = User.objects.create_user(username='regular', password='pass12345', department='Відділ А')
        self.admin_user = User.objects.create_user(username='staffer', password='pass12345', is_staff=True)

    def test_regular_user_message_creates_thread_visible_to_admin(self):
        self.client.force_login(self.regular_user)
        self.client.post(
            reverse('chat:send'),
            data=json.dumps({'chat_type': 'private', 'message': 'Потрібна допомога'}),
            content_type='application/json',
        )
        self.client.logout()

        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('chat:threads'))
        data = response.json()
        self.assertEqual(len(data['threads']), 1)
        self.assertEqual(data['threads'][0]['username'], 'regular')
        self.assertEqual(data['threads'][0]['department'], 'Відділ А')
        self.assertEqual(data['threads'][0]['unread_count'], 1)

    def test_admin_viewing_thread_marks_messages_read(self):
        PrivateChatMessage.objects.create(
            sender=self.regular_user, recipient_kind=PrivateChatMessage.RECIPIENT_USER,
            recipient_id=self.regular_user.id, message='Допоможіть', is_admin=False, is_read=False,
        )
        self.client.force_login(self.admin_user)
        self.client.get(reverse('chat:messages'), {'type': 'private', 'target_id': self.regular_user.id})
        self.assertTrue(
            PrivateChatMessage.objects.filter(recipient_id=self.regular_user.id, is_read=True).exists()
        )

    def test_non_staff_cannot_list_threads(self):
        self.client.force_login(self.regular_user)
        response = self.client.get(reverse('chat:threads'))
        self.assertNotEqual(response.status_code, 200)
