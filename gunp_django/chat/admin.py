from django.contrib import admin

from .models import PrivateChatMessage, PublicChatMessage


@admin.register(PublicChatMessage)
class PublicChatMessageAdmin(admin.ModelAdmin):
    list_display = ['sender_name', 'message', 'created_at']
    search_fields = ['sender_name', 'message']


@admin.register(PrivateChatMessage)
class PrivateChatMessageAdmin(admin.ModelAdmin):
    list_display = ['sender', 'recipient_kind', 'recipient_id', 'message', 'is_admin', 'is_read', 'created_at']
    list_filter = ['recipient_kind', 'is_admin', 'is_read']
