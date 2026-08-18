import logging
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


def check_ping(ip_address):
    if not ip_address:
        return {'status': False, 'latency': None}
    try:
        param = '-n' if os.name == 'nt' else '-c'
        start_time = time.time()
        result = subprocess.run(
            ['ping', param, '1', ip_address], capture_output=True, text=True, timeout=2,
        )
        latency = (time.time() - start_time) * 1000
        status = result.returncode == 0
        return {'status': status, 'latency': latency if status else None}
    except Exception as e:
        logger.error('Ping failed for %s: %s', ip_address, e)
        return {'status': False, 'latency': None}


def check_departments(departments):
    """Ping a list of Department objects in parallel, return list of (dept, result) tuples."""
    with ThreadPoolExecutor(max_workers=10) as executor:
        return list(executor.map(lambda dept: (dept, check_ping(dept.ip_address)), departments))


def refresh_department_statuses():
    """Ping every department with an IP and persist the results. Returns the count updated."""
    from django.utils import timezone

    from .models import Department

    departments = list(Department.objects.exclude(ip_address__isnull=True).exclude(ip_address=''))
    results = check_departments(departments)
    now = timezone.now()
    for dept, result in results:
        dept.last_status = result['status']
        dept.last_latency = result['latency']
        dept.last_checked = now
    if results:
        Department.objects.bulk_update(
            [d for d, _ in results], ['last_status', 'last_latency', 'last_checked'],
        )
    return len(results)


def generate_chatbot_response(message, support_request_model):
    message = (message or '').lower().strip()

    if 'не опрацьовані заявки' in message or 'показати не опрацьовані' in message:
        requests = support_request_model.objects.filter(status='new').order_by('-created_at')[:5]
        if requests:
            response = 'Не опрацьовані заявки:\n'
            for req in requests:
                response += f'- #{req.id}: {req.issue_type}, Дата: {req.created_at.strftime("%d.%m.%Y %H:%M")}\n'
            response += "Напишіть 'Заявка #номер' для деталей."
        else:
            response = 'Наразі немає не опрацьованих заявок.'
        return response

    if 'заявка' in message or 'запит' in message:
        number_match = re.search(r'#(\d+)', message) or re.search(r'номер (\d+)', message)
        if number_match:
            request_id = int(number_match.group(1))
            support_request = support_request_model.objects.filter(pk=request_id).first()
            if support_request:
                status_text = dict(support_request_model.STATUS_CHOICES).get(support_request.status, 'Невідомий')
                return (
                    f'Заявка #{support_request.id}:\n'
                    f'- Статус: {status_text}\n'
                    f'- Тип проблеми: {support_request.issue_type}\n'
                    f'- Дата створення: {support_request.created_at.strftime("%d.%m.%Y %H:%M")}\n'
                    f'Для деталей зверніться до техпідтримки.'
                )
            return f'Заявку з номером #{request_id} не знайдено. Перевірте номер або створіть нову заявку.'
        if 'мої заявки' in message or 'список заявок' in message:
            requests = support_request_model.objects.order_by('-created_at')[:5]
            if requests:
                response = 'Останні заявки:\n'
                for req in requests:
                    status_text = dict(support_request_model.STATUS_CHOICES).get(req.status, 'Невідомий')
                    response += f'- #{req.id}: {req.issue_type}, Статус: {status_text}\n'
                response += "Напишіть 'Заявка #номер' для деталей."
            else:
                response = 'Заявки відсутні. Створіть нову на сторінці техпідтримки.'
            return response
        return (
            "Напишіть 'Заявка #номер' для перевірки статусу, 'Мої заявки' для списку останніх заявок "
            "або 'Показати не опрацьовані заявки' для перегляду нових заявок.\n"
            "Також можете створити нову заявку на сторінці техпідтримки."
        )

    if 'ip' in message or 'айпі' in message or 'айпи' in message:
        ip_match = re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', message)
        if ip_match:
            ip = ip_match.group()
            return f"Ваша IP-адреса: {ip}. Для перевірки підключення спробуйте команду 'ping {ip}'"
        return "Я можу допомогти з IP-адресою. Напишіть 'Моя IP' або введіть вашу IP у форматі XXX.XXX.XXX.XXX"

    if 'mac' in message or 'мак' in message or 'фізична адреса' in message:
        mac_match = re.search(r'([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})', message)
        if mac_match:
            return f'Ваша MAC-адреса: {mac_match.group()}. Для зміни MAC-адреси зверніться до адміністратора.'
        return "Вкажіть вашу MAC-адресу у форматі XX:XX:XX:XX:XX:XX або напишіть 'Де знайти MAC?'"

    if 'привіт' in message or 'вітаю' in message:
        return "Вітаю! Я чат-бот техпідтримки ГУНП. Чим можу допомогти? Напишіть 'Заявка #номер' для перевірки статусу."

    if 'проблема' in message or 'не працює' in message or 'не можу' in message:
        return (
            'Опишіть проблему детальніше або створіть заявку на сторінці техпідтримки.\n'
            'Наприклад:\n- Не працює інтернет\n- Не відкривається внутрішній сайт\n- Проблеми з принтером\n'
            "Вкажіть вашу IP та MAC-адресу або напишіть 'Мої заявки' для перегляду статусу."
        )

    if 'допомога' in message or 'можеш' in message:
        return (
            'Я можу допомогти з:\n'
            "- Перевіркою статусу заявок ('Заявка #номер' або 'Мої заявки')\n"
            "- Переглядом не опрацьованих заявок ('Показати не опрацьовані заявки')\n"
            '- Визначенням IP/MAC адреси\n'
            '- Основними проблемами з підключенням\n'
            "Напишіть конкретний запит, наприклад 'Не працює інтернет' або 'Заявка #123'."
        )

    if 'дякую' in message or 'спасибі' in message:
        return 'Було приємно допомогти! Звертайтеся ще.'

    return (
        'Не розпізнав ваш запит. Ось що я можу:\n'
        "- Перевірити статус заявки ('Заявка #номер')\n"
        "- Показати останні заявки ('Мої заявки')\n"
        "- Показати не опрацьовані заявки ('Показати не опрацьовані заявки')\n"
        '- Допомогти з IP/MAC адресами\n'
        '- Пояснити, як вирішити прості технічні проблеми\n'
        'Спробуйте сформулювати запит інакше.'
    )
