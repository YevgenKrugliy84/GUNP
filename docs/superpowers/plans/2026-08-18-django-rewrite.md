# GUNP Django Rewrite Implementation Plan

> **For agentic workers:** Execute inline in the current session (not subagent-driven) — this is a single tightly-coupled framework migration where splitting across fresh subagents would cost more in re-derived context than it saves. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Replace the existing Flask/Flask-SocketIO app (`GUNP/app.py`, 2053 lines + dead `admin.py`) with a Django project delivering the same functionality, fixing known bugs, preserving existing data, running on `10.111.16.6:4040`, with an admin login `admin` / `PowerEdge123`.

**Architecture:** New Django project `gunp_django/` created alongside the existing Flask app inside `GUNP/` (old app left in place, untouched, as a reference/rollback until the new app is verified). Standard Django (WSGI, sync views) — no Channels/ASGI. Real-time chat becomes short-interval AJAX polling instead of Socket.IO, to avoid adding Redis/ASGI infra for a low-traffic internal tool. Back-office CRUD (departments, records, support requests, knowledge base, users) is delivered through the built-in Django admin site instead of hand-written add/edit/delete templates — this alone removes roughly 700 of the original 2053 lines of route code. Existing SQLite data (`instance/gundatabase.db`) is migrated into the new schema by a one-off management command instead of being discarded.

**Tech Stack:** Django 5.x, SQLite (existing engine, no infra change), Django's built-in auth (`AbstractUser` + `is_staff` for "admin"), Django admin, vanilla JS (fetch + `setInterval`) for chat/status polling — no new frontend framework.

**Spec:** This plan doc is self-contained; the source of truth for existing behavior is `GUNP/app.py` (Flask) and the (dead, unused) `GUNP/admin.py`, both read in full before writing this plan.

## Global Constraints

- Host/port for `runserver`: `10.111.16.6:4040`. `ALLOWED_HOSTS` must include `10.111.16.6`.
- Admin login: username `admin`, password `PowerEdge123`, created via a data migration (not left as the old `admin123` default).
- Do not delete or overwrite `GUNP/instance/gundatabase.db` — read-only source for the data-import command.
- Do not run the new project on port 5000 (old Flask app's port) to avoid collision during side-by-side verification.
- `GUNP/admin.py` is dead code (never imported by `app.py`, references undefined `current_user`/`logging`/`abort`/`User`) — delete it once the Django app is confirmed working, not before.
- Keep secrets (`SECRET_KEY`, admin password) out of version control: load from environment with safe local defaults in a `.env`-style file that is gitignored.

---

## File Structure

```
GUNP/
  gunp_django/
    manage.py
    gunp/                      # project package
      __init__.py
      settings.py
      urls.py
      wsgi.py
    directory/                 # core app: departments, records, public pages, tech support, tools
      __init__.py
      models.py                # Department, Record, KnowledgeBaseArticle, SupportRequest, DownloadLog
      admin.py                 # Django admin registrations (replaces admin/*.html CRUD)
      views.py                 # index, department detail, search, tech_support, resources, about, tools
      forms.py                 # RecordForm, SupportRequestForm, DepartmentForm (WTForms -> Django forms)
      urls.py
      services.py              # check_ping(), department status aggregation, chatbot response generator
      management/commands/import_legacy_db.py   # one-off import from gundatabase.db
      templates/directory/...
    accounts/
      __init__.py
      models.py                # User(AbstractUser) with is_admin property = is_staff
      admin.py
      views.py                 # register, login, logout (regular users)
      forms.py
      urls.py
      templates/accounts/...
    chat/
      __init__.py
      models.py                # PublicChatMessage, PrivateChatMessage
      admin.py
      views.py                 # chat page + send/list JSON endpoints (polling)
      urls.py
      templates/chat/...
    static/                    # copied from GUNP/static (js, images)
    templates/base.html        # copied/adapted from GUNP/templates/base.html
    requirements.txt
    .env.example
  docs/superpowers/plans/2026-08-18-django-rewrite.md   # this file
```

---

## Task 1: Project scaffold, settings, host/port

**Files:**
- Create: `GUNP/gunp_django/manage.py`, `GUNP/gunp_django/gunp/settings.py`, `GUNP/gunp_django/gunp/urls.py`, `GUNP/gunp_django/gunp/wsgi.py`
- Create: `GUNP/gunp_django/requirements.txt`, `GUNP/gunp_django/.env.example`

**Interfaces:**
- Produces: Django project importable via `manage.py`; `INSTALLED_APPS` list that later tasks append `directory`, `accounts`, `chat` to; `AUTH_USER_MODEL = 'accounts.User'`.

- [x] Run `django-admin startproject gunp .` inside `GUNP/gunp_django/`.
- [x] Set `ALLOWED_HOSTS = ['10.111.16.6', 'localhost', '127.0.0.1']` in `settings.py`.
- [x] Set `SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '<dev-fallback>')`, read from `.env` via `python-decouple` or plain `os.environ` + `django-environ`.
- [x] Set `DATABASES['default']` to `sqlite3` pointing at `GUNP/gunp_django/db.sqlite3` (fresh file, separate from the legacy `instance/gundatabase.db`).
- [x] Add `LOGIN_URL = 'accounts:login'`, `LOGIN_REDIRECT_URL = 'directory:index'`, `LOGOUT_REDIRECT_URL = 'directory:index'`.
- [x] Write `requirements.txt`: `Django>=5.0,<5.1`, `python-decouple` (or `django-environ`), `speedtest-cli`.
- [x] Write `.env.example` documenting `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`.
- [x] Verify: `python manage.py check` runs with no errors (apps not added yet, so this just proves the project boots).

## Task 2: `accounts` app — custom User model, login/register/logout

**Files:**
- Create: `GUNP/gunp_django/accounts/models.py`, `admin.py`, `views.py`, `forms.py`, `urls.py`, `templates/accounts/login.html`, `templates/accounts/register.html`

**Interfaces:**
- Consumes: nothing (first domain app).
- Produces: `accounts.User` (extends `AbstractUser`, adds `department = CharField(blank=True)`; `is_admin` implemented as a `@property` returning `self.is_staff`, matching the old Flask distinction between `User` and `AdminUser`). URL names `accounts:login`, `accounts:logout`, `accounts:register`.

- [x] `models.py`: `class User(AbstractUser): department = models.CharField(max_length=100, blank=True)` + `is_admin` property.
- [x] Add `accounts` to `INSTALLED_APPS`, set `AUTH_USER_MODEL = 'accounts.User'` in settings (must happen before first migration).
- [x] `forms.py`: `RegistrationForm(UserCreationForm)` with `username`, `password1`, `password2`; a `Django AuthenticationForm` reused directly for login (no need to hand-roll — this replaces the old `LoginForm`).
- [x] `views.py`: `register` (FBV, redirects to `accounts:login` on success with a success message via `django.contrib.messages`); login/logout delegate to `django.contrib.auth.views.LoginView`/`LogoutView` in `urls.py` (do not hand-write session logic — this is what replaces the old duplicated `login`/`logout` routes in `app.py` and the dead `admin.py`).
- [x] `urls.py`: `path('register/', views.register, name='register')`, `path('login/', auth_views.LoginView.as_view(template_name='accounts/login.html'), name='login')`, `path('logout/', auth_views.LogoutView.as_view(), name='logout')`.
- [x] `templates/accounts/login.html`, `register.html`: adapt from `GUNP/templates/login.html` / `register.html`, extending the shared `base.html`.
- [x] Run `python manage.py makemigrations accounts && python manage.py migrate`.
- [x] Verify: `python manage.py runserver 10.111.16.6:4040`, visit `/accounts/register/`, create a user, log in, log out — confirm redirects match `LOGIN_REDIRECT_URL`/`LOGOUT_REDIRECT_URL`.

## Task 3: `directory` app — models + Django admin (replaces hand-rolled CRUD)

**Files:**
- Create: `GUNP/gunp_django/directory/models.py`, `admin.py`

**Interfaces:**
- Consumes: `accounts.User` (FK from `DownloadLog`).
- Produces: `Department`, `Record`, `SupportRequest`, `KnowledgeBaseArticle`, `DownloadLog` models; Django admin site fully wired for all back-office CRUD that used to live in `admin_bp` (`manage_departments`, `manage_records`, `manage_support_requests`, `manage_knowledge_base`, `manage_users` — ~700 lines of `app.py` retired in favor of `admin.py` registrations).

- [x] `models.py` — field-for-field port of the Flask models (`Department`, `Record`, `SupportRequest`, `KnowledgeBaseArticle`, `DownloadLog`), using Django `models.Model`, `ForeignKey(..., on_delete=models.CASCADE)`, `unique=True` on `Record.ip_address`/`mac_address`, `db_index=True` on `KnowledgeBaseArticle.title`/`category` (replaces the old `db.Index` table args).
- [x] Add IP/MAC format validation via `RegexValidator` on `Record.ip_address`/`mac_address` (same regexes as the old WTForms `Regexp` validators) so Django admin and any custom forms both enforce it.
- [x] `admin.py`:
  - `DepartmentAdmin(list_display=['name','ip_address','last_status','last_latency','last_checked'], search_fields=['name'])`
  - `RecordAdmin(list_display=['last_name','first_name','department','ip_address','mac_address','service','office'], list_filter=['department'], search_fields=['last_name','first_name','ip_address','mac_address'])` with a custom admin action `export_as_csv` (replaces `export_records`/`export_csv`) and CSV import wired through a custom admin template/view (replaces `manage_records` POST branch) — use `django-import-export` (add to `requirements.txt`) rather than hand-rolling CSV parsing, since it gives import *and* export for free with validation errors surfaced in the admin UI.
  - `SupportRequestAdmin(list_display=['id','name','department','issue_type','status','created_at'], list_filter=['status','urgency'], search_fields=['name','email'])`.
  - `KnowledgeBaseArticleAdmin(list_display=['title','category','updated_at'], list_filter=['category'], search_fields=['title','content'])`.
  - `DownloadLogAdmin(list_display=['user','filename','downloaded_at'])`, read-only (`has_add_permission` returns `False`).
- [x] Add `django-import-export` to `requirements.txt`, add it to `INSTALLED_APPS`.
- [x] Add `directory` to `INSTALLED_APPS`. Run `makemigrations directory && migrate`.
- [x] Verify: `python manage.py createsuperuser` (throwaway test creds), log into `/admin/`, confirm all five models are listed, add/edit/delete a `Department` and a `Record` through the admin UI, run the CSV export action on `Record` and confirm a valid CSV downloads.

## Task 4: Data migration from the legacy Flask SQLite DB

**Files:**
- Create: `GUNP/gunp_django/directory/management/commands/import_legacy_db.py`

**Interfaces:**
- Consumes: `GUNP/instance/gundatabase.db` (read-only, via stdlib `sqlite3`), `directory.models.Department`/`Record`/`SupportRequest`/`KnowledgeBaseArticle`.
- Produces: populated `db.sqlite3` for the new project.

- [x] Command opens `sqlite3.connect(str(Path(settings.BASE_DIR).parent / 'instance' / 'gundatabase.db'))` **read-only** (`sqlite3.connect(f'file:{path}?mode=ro', uri=True)`).
- [x] For each legacy table (`department`, `record`, `support_request`, `knowledge_base_article`), `SELECT *`, and `get_or_create`/`bulk_create` into the new models, mapping legacy `id`s to preserve FK relationships (import departments first, build an `{old_id: new_pk}` map, use it for `Record.department_id`/`SupportRequest.department_id`).
- [x] Wrap the whole import in `transaction.atomic()`; on any row error, log it with `self.stderr.write` and continue (don't abort the whole import for one bad row) — print a final summary count per table.
- [x] Make the command idempotent: skip rows whose natural key (`Record.ip_address`, `Department.name`) already exists, so it can be re-run safely.
- [x] Verify: `python manage.py import_legacy_db`, then `python manage.py shell -c "from directory.models import Department, Record; print(Department.objects.count(), Record.objects.count())"` and confirm counts are non-zero and match `sqlite3 instance/gundatabase.db "select count(*) from department"` / `record`.

## Task 5: Admin superuser with the required credentials

**Files:**
- Create: `GUNP/gunp_django/accounts/management/commands/create_default_admin.py`

**Interfaces:**
- Consumes: `accounts.User`.
- Produces: an idempotent way to guarantee the `admin`/`PowerEdge123` account exists.

- [x] Command: if `User.objects.filter(username='admin').exists()` is false, create `User.objects.create_superuser('admin', email='', password=os.environ.get('GUNP_ADMIN_PASSWORD', 'PowerEdge123'))`; if it exists, leave the password untouched (never silently reset a password someone may have already changed).
- [x] Document in `README.md` that the default password should be rotated after first login (same caveat the old code had, but now actually acted on since we don't hardcode it in dead code).
- [x] Verify: run the command twice — first run creates the account, second run is a no-op (prints "admin already exists"); log into `/admin/` with `admin`/`PowerEdge123`.

## Task 6: `directory` app — public views (index, department detail, search, tech support, tools)

**Files:**
- Create: `GUNP/gunp_django/directory/views.py`, `forms.py`, `urls.py`, `services.py`
- Create: `GUNP/gunp_django/directory/templates/directory/{index,department,search,tech_support,check_support_request,about,resources,network_tools,ip_calculator,public_add_record}.html`

**Interfaces:**
- Consumes: `directory.models.*`, `services.check_ping(ip)`, `services.generate_chatbot_response(message)`.
- Produces: URL names `directory:index`, `directory:department`, `directory:search`, `directory:tech_support`, `directory:submit_support_request`, `directory:check_support_request`, `directory:about`, `directory:resources`, `directory:network_tools`, `directory:ip_calculator`, `directory:add_record_public`, `directory:department_statuses` (JSON), `directory:chatbot` (JSON).

- [x] `services.py`: port `check_ping()` unchanged (subprocess ping, `-c`/`-n` by `os.name`); port `generate_chatbot_response()` unchanged (pure function, no Flask dependency, straightforward copy).
- [x] `forms.py`: `RecordForm(forms.ModelForm)` (Meta.model = Record, same fields, reuses the model-level `RegexValidator`s from Task 3 instead of redefining regexes); `SupportRequestForm` similarly as a `ModelForm`.
- [x] `views.index`: list departments ordered by name — template renders status dot from `last_status`/`last_latency` (same as old `index.html`), but pings are computed on-demand by JS calling `department_statuses` (see below) rather than only every 5 minutes by a background job, since Task 1 deliberately drops the old `os.remove('gundatabase.db')`-on-boot + APScheduler pattern in favor of one-off/on-demand computation — call this out in the final recommendations doc as an area to revisit if department count grows large.
- [x] `views.department_statuses`: `JsonResponse` — same shape as the old `/admin/department-statuses` endpoint but public (read-only status info isn't sensitive), using `ThreadPoolExecutor` exactly as before.
- [x] `views.department_detail`: `@login_required`, 404 via `get_object_or_404`, lists that department's records.
- [x] `views.add_record_public`: public record-submission form scoped to one department; validate via `RecordForm`, catch `IntegrityError` for duplicate IP/MAC (replaces the old manual `.filter_by(...).first()` existence checks — let the DB's `unique=True` constraint be the source of truth, catch `IntegrityError`, show a form error).
- [x] `views.search`: `@login_required`; `Record.objects.filter(Q(last_name__icontains=term) | Q(first_name__icontains=term) | ...)`.
- [x] `views.tech_support`, `submit_support_request`, `check_support_request`: straightforward ports.
- [x] `views.about`, `resources` (with `?search=` filtering via `Q`), `network_tools` (ping via subprocess, **fix the Linux/Windows bug**: the old code always shelled out to `tracert` even on Linux — use `traceroute` when `os.name != 'nt'`), `ip_calculator`, `chatbot` (JSON POST endpoint wrapping `services.generate_chatbot_response`).
- [x] `urls.py` wiring all of the above; include it from the project `urls.py` at `path('', include('directory.urls'))`.
- [x] `templates/directory/*.html`: adapt directly from the existing Jinja templates in `GUNP/templates/*.html` — Django template syntax is a near-superset for these (loops/if/url_for→url tag/csrf_token differences); copy content and mechanically translate `{{ url_for('x') }}` → `{% url 'directory:x' %}`, `{% csrf_token %}` added to every `<form method="post">`.
- [x] Verify: `python manage.py runserver 10.111.16.6:4040`; manually exercise `/`, a department detail page, `/search/`, `/tech-support/`, submit a support request, `/resources/`, `/network-tools/` (ping a known-good host), `/ip-calculator/`.

## Task 7: `chat` app — polling-based chat (replaces Socket.IO)

**Files:**
- Create: `GUNP/gunp_django/chat/models.py`, `admin.py`, `views.py`, `urls.py`, `templates/chat/chat.html`, `static/chat/chat.js`

**Interfaces:**
- Consumes: `accounts.User`, `directory.models.Department`.
- Produces: URL names `chat:room` (page), `chat:send` (POST JSON), `chat:messages` (GET JSON, polled).

- [x] `models.py`: `PublicChatMessage(sender, message, created_at)`, `PrivateChatMessage(sender, recipient_kind, recipient_id, message, created_at, is_read)` — collapse the old `user_id`/`guest_id`/`dept_`-prefix string hacks into an explicit `recipient_kind = CharField(choices=[('user','User'),('department','Department')])` + `recipient_id = IntegerField()`, which is what the old `f'dept_{target_id}'` string-prefix convention was really encoding; this removes an entire class of string-parsing bugs the Flask version had (e.g. `msg.user_id.startswith('dept_')` calls that would `AttributeError` on `None`).
- [x] `views.send_message`: `@login_required @require_POST`, writes a `PublicChatMessage` or `PrivateChatMessage` depending on posted `chat_type`, returns the created message as JSON.
- [x] `views.list_messages`: `@login_required`, `?type=public|private|stats&since=<id>` — returns messages newer than `since` (id-based cursor, not full history every call) as JSON; this is the piece that replaces `socketio.emit`/`@socketio.on('send_message')`.
- [x] `views.chat_room`: renders `chat/chat.html` with initial message history + the target list (departments for stats chat, "admin" for private chat) exactly like the old `user_chat`/`admin_chats` context building, but without the Socket.IO room bookkeeping (`online_users` dict, `join_room` calls) — presence ("who's online") is dropped as a feature; call this out explicitly in the recommendations doc as a deliberate scope cut, not an oversight.
- [x] `static/chat/chat.js`: `setInterval(fetchNewMessages, 3000)` calling `chat:messages?since=<lastId>`, appends to the DOM; POST via `fetch` to `chat:send` on form submit.
- [x] `urls.py`, register in project `urls.py` under `path('chat/', include('chat.urls'))`.
- [x] Verify: log in as two different users in two browser profiles, open `/chat/`, send a public message from one, confirm it appears in the other within ~3s without a page reload.

## Task 8: Retire the Flask app, wire up the run command, write recommendations

**Files:**
- Modify: `GUNP/README.md`
- Delete: `GUNP/admin.py` (confirmed dead in exploration — never imported, references undefined names)
- Create: `GUNP/gunp_django/run.sh` (or documented `manage.py runserver` invocation)
- Create: `GUNP/docs/modernization-recommendations.md`

- [x] Delete `GUNP/admin.py`.
- [x] `README.md`: replace with setup/run instructions for the Django project — `pip install -r gunp_django/requirements.txt`, `python gunp_django/manage.py migrate`, `python gunp_django/manage.py import_legacy_db`, `python gunp_django/manage.py create_default_admin`, `python gunp_django/manage.py runserver 10.111.16.6:4040`.
- [x] Write `docs/modernization-recommendations.md` covering (content drafted in the chat reply to the user, then saved here): dependency pinning/`pip-audit`, moving `SECRET_KEY`/admin password fully to environment/secrets manager before any real deployment, switching from `runserver` to `gunicorn`+`nginx` (or `waitress` on Windows) for anything beyond a dev/demo box, adding a `django-import-export`-based CSV workflow already covered in Task 3, adding `django-axes` or similar for login rate-limiting (the old app had no lockout at all), moving the ping sweep to a proper scheduled job (`django-crontab`/systemd timer) instead of on-demand `ThreadPoolExecutor` calls if department count grows, and — if live chat presence/typing indicators become a real requirement — revisiting Django Channels + Redis at that point rather than upfront.
- [x] Verify: fresh clone/venv, follow the README top-to-bottom, confirm the app comes up on `10.111.16.6:4040` and `admin`/`PowerEdge123` logs into `/admin/`.

---

## Self-Review Notes

- **Spec coverage:** every route in the original `app.py` maps to a task above except the 5-minute `BackgroundScheduler` ping sweep and Socket.IO presence list, both deliberately cut and documented in Tasks 6–8 rather than silently dropped.
- **DB-wipe bug:** fixed by construction — Task 1 creates a fresh `db.sqlite3` once; nothing in the new project ever calls `os.remove` on it, and Task 4's importer is read-only against the legacy file and idempotent against the new one.
- **Dead code:** `GUNP/admin.py` deletion is deferred to Task 8 (after the new app is verified end-to-end), not done speculatively early.
- **Linux/Windows bug:** the hardcoded `tracert` call is fixed in Task 6.
- **Type/name consistency:** `directory`, `accounts`, `chat` app names and their URL namespaces are used consistently from Task 1 onward.
