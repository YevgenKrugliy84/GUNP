import json

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from directory.models import Department

from .models import PrivateChatMessage, PublicChatMessage

User = get_user_model()


def _serialize_public(msg, request_user):
    return {
        'id': msg.id,
        'message': msg.message,
        'sender_name': msg.sender_name,
        'created_at': msg.created_at.isoformat(),
        'is_admin': bool(msg.sender_id and msg.sender.is_staff),
        'is_mine': msg.sender_id == request_user.id,
    }


def _serialize_private(msg, request_user):
    return {
        'id': msg.id,
        'message': msg.message,
        'sender_name': 'Адміністратор' if msg.is_admin else (msg.sender.username if msg.sender else 'Гість'),
        'created_at': msg.created_at.isoformat(),
        'is_admin': msg.is_admin,
        'is_mine': msg.sender_id == request_user.id,
    }


@login_required
def chat_room(request):
    departments = Department.objects.order_by('name')
    user_department = None
    if not request.user.is_staff and request.user.department:
        user_department = Department.objects.filter(name=request.user.department).first()
    return render(request, 'chat/chat.html', {'departments': departments, 'user_department': user_department})


@login_required
@require_GET
def list_messages(request):
    chat_type = request.GET.get('type', 'public')
    since = int(request.GET.get('since', 0) or 0)

    if chat_type == 'public':
        qs = PublicChatMessage.objects.filter(id__gt=since).order_by('created_at')[:200]
        return JsonResponse({'messages': [_serialize_public(m, request.user) for m in qs]})

    if chat_type in ('private', 'stats'):
        if chat_type == 'private':
            recipient_kind = PrivateChatMessage.RECIPIENT_USER
            target_id = request.GET.get('target_id')
            recipient_id = int(target_id) if target_id else request.user.id
        else:
            recipient_kind = PrivateChatMessage.RECIPIENT_DEPARTMENT
            target_id = request.GET.get('target_id')
            if not target_id:
                return JsonResponse({'messages': []})
            recipient_id = int(target_id)

        qs = PrivateChatMessage.objects.filter(
            recipient_kind=recipient_kind, recipient_id=recipient_id, id__gt=since,
        ).order_by('created_at')[:200]
        messages = [_serialize_private(m, request.user) for m in qs]
        if request.user.is_staff:
            PrivateChatMessage.objects.filter(
                recipient_kind=recipient_kind, recipient_id=recipient_id, is_admin=False, is_read=False,
            ).update(is_read=True)
        return JsonResponse({'messages': messages})

    return JsonResponse({'messages': []})


@user_passes_test(lambda u: u.is_staff)
@require_GET
def list_private_threads(request):
    """Admin-only: one row per distinct user who has an active private conversation."""
    recipient_ids = (
        PrivateChatMessage.objects.filter(recipient_kind=PrivateChatMessage.RECIPIENT_USER)
        .values_list('recipient_id', flat=True)
        .distinct()
    )
    threads = []
    for recipient_id in recipient_ids:
        thread_messages = PrivateChatMessage.objects.filter(
            recipient_kind=PrivateChatMessage.RECIPIENT_USER, recipient_id=recipient_id,
        )
        last_message = thread_messages.order_by('-created_at').first()
        if not last_message:
            continue
        user = User.objects.filter(pk=recipient_id).first()
        unread_count = thread_messages.filter(is_admin=False, is_read=False).count()
        threads.append({
            'user_id': recipient_id,
            'username': user.username if user else f'Користувач #{recipient_id}',
            'department': user.department if user else '',
            'last_message': last_message.message,
            'last_message_at': last_message.created_at.isoformat(),
            'unread_count': unread_count,
        })
    threads.sort(key=lambda t: t['last_message_at'], reverse=True)
    return JsonResponse({'threads': threads})


@login_required
@require_POST
def send_message(request):
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        data = request.POST

    chat_type = data.get('chat_type')
    message_text = (data.get('message') or '').strip()
    target_id = data.get('target_id')

    if not chat_type or not message_text:
        return JsonResponse({'error': 'Повідомлення або тип чату не вказано'}, status=400)

    if chat_type == 'public':
        msg = PublicChatMessage.objects.create(
            sender=request.user, sender_name=request.user.username, message=message_text,
        )
        return JsonResponse(_serialize_public(msg, request.user))

    if chat_type in ('private', 'stats'):
        if chat_type == 'private':
            recipient_kind = PrivateChatMessage.RECIPIENT_USER
            recipient_id = int(target_id) if target_id else request.user.id
        else:
            if not target_id:
                return JsonResponse({'error': 'Не вказано відділ'}, status=400)
            recipient_kind = PrivateChatMessage.RECIPIENT_DEPARTMENT
            recipient_id = int(target_id)

        msg = PrivateChatMessage.objects.create(
            sender=request.user,
            recipient_kind=recipient_kind,
            recipient_id=recipient_id,
            message=message_text,
            is_admin=request.user.is_staff,
            is_read=request.user.is_staff,
        )
        return JsonResponse(_serialize_private(msg, request.user))

    return JsonResponse({'error': 'Невідомий тип чату'}, status=400)
