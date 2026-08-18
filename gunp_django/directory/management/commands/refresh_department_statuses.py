from django.core.management.base import BaseCommand

from directory.services import refresh_department_statuses


class Command(BaseCommand):
    help = 'Pings every department with an IP address and caches last_status/last_latency/last_checked.'

    def handle(self, *args, **options):
        count = refresh_department_statuses()
        self.stdout.write(self.style.SUCCESS(f'Refreshed statuses for {count} department(s).'))
