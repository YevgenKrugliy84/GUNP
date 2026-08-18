import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

DEFAULT_USERNAME = 'admin'
DEFAULT_PASSWORD = 'PowerEdge123'


class Command(BaseCommand):
    help = 'Ensures the default GUNP admin account exists (idempotent, never resets an existing password).'

    def handle(self, *args, **options):
        User = get_user_model()
        if User.objects.filter(username=DEFAULT_USERNAME).exists():
            self.stdout.write(self.style.WARNING(f'User "{DEFAULT_USERNAME}" already exists — leaving it untouched.'))
            return
        password = os.environ.get('GUNP_ADMIN_PASSWORD', DEFAULT_PASSWORD)
        User.objects.create_superuser(username=DEFAULT_USERNAME, email='', password=password)
        self.stdout.write(self.style.SUCCESS(f'Created default admin user "{DEFAULT_USERNAME}".'))
