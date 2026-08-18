from django.conf import settings
from django.db import models


class PublicChatMessage(models.Model):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='public_messages')
    sender_name = models.CharField(max_length=100)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.sender_name}: {self.message[:30]}'


class PrivateChatMessage(models.Model):
    RECIPIENT_USER = 'user'
    RECIPIENT_DEPARTMENT = 'department'
    RECIPIENT_CHOICES = [
        (RECIPIENT_USER, 'Користувач'),
        (RECIPIENT_DEPARTMENT, 'Відділ'),
    ]

    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='private_messages')
    recipient_kind = models.CharField(max_length=20, choices=RECIPIENT_CHOICES, default=RECIPIENT_USER)
    recipient_id = models.IntegerField()
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_admin = models.BooleanField(default=False)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.sender}: {self.message[:30]}'
