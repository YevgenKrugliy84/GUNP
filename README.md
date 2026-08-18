# GUNP — Django-версія

Внутрішній портал УІАП ГУНП у м. Києві: облік ІТ-записів по підрозділах, техпідтримка,
чат, база знань, мережеві інструменти. Раніше був написаний на Flask (`app.py`,
залишений у цій директорії як довідковий/резервний варіант — не запускайте його
одночасно з Django-версією на тому ж порту). Тепер — на Django.

## Швидкий старт

```bash
cd GUNP
python3 -m venv gunp_django_venv
source gunp_django_venv/bin/activate
pip install -r gunp_django/requirements.txt

cd gunp_django
python manage.py migrate
python manage.py import_legacy_db      # переносить дані зі старої instance/gundatabase.db (безпечно, ідемпотентно)
export GUNP_ADMIN_PASSWORD='свій-надійний-пароль'
python manage.py create_default_admin  # створює admin/$GUNP_ADMIN_PASSWORD, якщо ще не існує
python manage.py runserver 10.111.16.6:4040
```

Сайт: http://10.111.16.6:4040/
Адмінка: http://10.111.16.6:4040/admin/ — логін `admin`, пароль — той, що задали через `GUNP_ADMIN_PASSWORD`
(якщо змінну не задати, команда згенерує випадковий пароль і виведе його одноразово в консоль —
його ніде більше не зберігають, тож одразу занотуйте).

**Обов'язково змініть пароль адміністратора після першого входу** (Адмінка → Users → admin →
"This form does not allow raw password" → посилання "change password form").

## Змінні середовища (`.env`, див. `gunp_django/.env.example`)

- `DJANGO_SECRET_KEY` — секретний ключ Django, обов'язково задати свій перед реальним запуском.
- `DJANGO_DEBUG` — `True`/`False`.
- `GUNP_ADMIN_PASSWORD` — пароль для `create_default_admin`, якщо облікового запису `admin` ще немає
  (не задано — команда згенерує й виведе випадковий пароль замість фіксованого дефолту).

## Структура

- `directory/` — підрозділи, записи, заявки техпідтримки, база знань, публічні сторінки.
- `accounts/` — користувачі, вхід/реєстрація/вихід.
- `chat/` — чат (AJAX-polling, без Socket.IO/Channels).
- Адмінка Django (`/admin/`) — весь CRUD для підрозділів/записів/заявок/бази знань/користувачів,
  включно з імпортом/експортом CSV (django-import-export) для записів.

Детальні рекомендації з подальшої модернізації — у `docs/modernization-recommendations.md`.
