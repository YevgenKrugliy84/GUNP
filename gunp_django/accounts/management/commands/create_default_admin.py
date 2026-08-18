import os
import secrets
import string

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

DEFAULT_USERNAME = 'admin'


def _generate_password(length=20):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


class Command(BaseCommand):
    help = 'Ensures the default GUNP admin account exists (idempotent, never resets an existing password).'

    def handle(self, *args, **options):
        User = get_user_model()
        if User.objects.filter(username=DEFAULT_USERNAME).exists():
            self.stdout.write(self.style.WARNING(f'User "{DEFAULT_USERNAME}" already exists — leaving it untouched.'))
            return
        password = os.environ.get('GUNP_ADMIN_PASSWORD')
        generated = password is None
        if generated:
            password = _generate_password()
        User.objects.create_superuser(username=DEFAULT_USERNAME, email='', password=password)
        self.stdout.write(self.style.SUCCESS(f'Created default admin user "{DEFAULT_USERNAME}".'))
        if generated:
            self.stdout.write(self.style.WARNING(
                f'GUNP_ADMIN_PASSWORD was not set — generated a random password: {password}\n'
                'Save it now; it is not stored anywhere else.'
            ))
