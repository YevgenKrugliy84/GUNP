"""
Django settings for the GUNP project.
"""

import os
from pathlib import Path

from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config(
    'DJANGO_SECRET_KEY',
    default='django-insecure-dev-only-change-me-before-any-real-deployment',
)

DEBUG = config('DJANGO_DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = ['10.111.16.6', 'localhost', '127.0.0.1']

CSRF_TRUSTED_ORIGINS = [
    'http://10.111.16.6:8095',
    'http://localhost:8095',
    'http://127.0.0.1:8095',
]


INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'import_export',
    'accounts',
    'directory',
    'chat',
]

JAZZMIN_SETTINGS = {
    'site_title': 'GUNP — Адмінпанель',
    'site_header': 'ГУНП у м. Києві',
    'site_brand': 'УІАП ГУНП',
    'welcome_sign': 'Адміністративна панель УІАП ГУНП у м. Києві',
    'copyright': 'УІАП ГУНП у м. Києві',
    'search_model': ['directory.Record', 'directory.Department'],
    'show_ui_builder': False,
    'navigation_expanded': True,
    'topmenu_links': [
        {'name': 'На сайт', 'url': 'directory:index', 'permissions': []},
        {'name': 'Чат', 'url': 'chat:room', 'permissions': ['auth.view_user']},
    ],
    'icons': {
        'auth.user': 'fas fa-user',
        'accounts.user': 'fas fa-user',
        'auth.Group': 'fas fa-users',
        'directory.department': 'fas fa-building',
        'directory.record': 'fas fa-address-card',
        'directory.supportrequest': 'fas fa-life-ring',
        'directory.knowledgebasearticle': 'fas fa-book',
        'directory.downloadlog': 'fas fa-download',
        'chat.publicchatmessage': 'fas fa-comments',
        'chat.privatechatmessage': 'fas fa-comment-dots',
    },
    'default_icon_parents': 'fas fa-chevron-circle-right',
    'default_icon_children': 'fas fa-circle',
    'order_with_respect_to': ['directory', 'accounts', 'chat', 'auth'],
}

JAZZMIN_UI_TWEAKS = {
    'theme': 'flatly',
    'dark_mode_theme': 'darkly',
    'navbar': 'navbar-dark',
    'brand_colour': 'navbar-primary',
    'accent': 'accent-primary',
    'sidebar': 'sidebar-dark-primary',
    'no_navbar_border': True,
    'button_classes': {
        'primary': 'btn-primary',
        'secondary': 'btn-secondary',
        'info': 'btn-info',
        'warning': 'btn-warning',
        'danger': 'btn-danger',
        'success': 'btn-success',
    },
}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'gunp.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'gunp.wsgi.application'


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'directory:index'
LOGOUT_REDIRECT_URL = 'directory:index'

LANGUAGE_CODE = 'uk'
TIME_ZONE = 'Europe/Kyiv'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {'format': '%(asctime)s - %(levelname)s - %(name)s - %(message)s'},
    },
    'handlers': {
        'file': {
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'app.log',
            'formatter': 'default',
        },
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'default',
        },
    },
    'root': {
        'handlers': ['file', 'console'],
        'level': 'INFO',
    },
}
