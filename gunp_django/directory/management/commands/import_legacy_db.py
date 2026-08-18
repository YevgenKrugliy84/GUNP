import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.dateparse import parse_datetime

from directory.models import Department, KnowledgeBaseArticle, Record, SupportRequest


def _legacy_db_path():
    return Path(settings.BASE_DIR).parent / 'instance' / 'gundatabase.db'


class Command(BaseCommand):
    help = 'Imports departments/records/support requests/knowledge base articles from the legacy Flask SQLite DB (read-only, idempotent).'

    def handle(self, *args, **options):
        db_path = _legacy_db_path()
        if not db_path.exists():
            self.stderr.write(self.style.ERROR(f'Legacy database not found at {db_path}'))
            return

        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        dept_id_map = {}
        created = {'department': 0, 'record': 0, 'support_request': 0, 'knowledge_base_article': 0}
        skipped = {'department': 0, 'record': 0, 'support_request': 0, 'knowledge_base_article': 0}

        with transaction.atomic():
            for row in cur.execute('SELECT * FROM department'):
                existing = Department.objects.filter(name=row['name']).first()
                if existing:
                    dept_id_map[row['id']] = existing.id
                    skipped['department'] += 1
                    continue
                dept = Department.objects.create(
                    name=row['name'],
                    ip_address=row['ip_address'],
                    last_status=bool(row['last_status']),
                    last_latency=row['last_latency'],
                    last_checked=parse_datetime(row['last_checked']) if row['last_checked'] else None,
                )
                dept_id_map[row['id']] = dept.id
                created['department'] += 1

            for row in cur.execute('SELECT * FROM record'):
                if Record.objects.filter(ip_address=row['ip_address']).exists():
                    skipped['record'] += 1
                    continue
                new_dept_id = dept_id_map.get(row['department_id'])
                if new_dept_id is None:
                    self.stderr.write(self.style.WARNING(
                        f"Skipping record {row['id']}: unknown legacy department_id={row['department_id']}"
                    ))
                    continue
                Record.objects.create(
                    department_id=new_dept_id,
                    last_name=row['last_name'],
                    first_name=row['first_name'],
                    middle_name=row['middle_name'],
                    ip_address=row['ip_address'],
                    mac_address=row['mac_address'],
                    service=row['service'],
                    office=row['office'],
                    work_phone=row['work_phone'],
                    mobile_phone=row['mobile_phone'],
                )
                created['record'] += 1

            for row in cur.execute('SELECT * FROM support_request'):
                new_dept_id = dept_id_map.get(row['department_id']) if row['department_id'] else None
                SupportRequest.objects.create(
                    name=row['name'],
                    department_id=new_dept_id,
                    email=row['email'],
                    issue_type=row['issue_type'],
                    description=row['description'],
                    urgency=row['urgency'],
                    status=row['status'],
                    admin_response=row['admin_response'],
                )
                created['support_request'] += 1

            for row in cur.execute('SELECT * FROM knowledge_base_article'):
                if KnowledgeBaseArticle.objects.filter(title=row['title']).exists():
                    skipped['knowledge_base_article'] += 1
                    continue
                KnowledgeBaseArticle.objects.create(
                    title=row['title'], content=row['content'], category=row['category'],
                )
                created['knowledge_base_article'] += 1

        conn.close()
        self.stdout.write(self.style.SUCCESS(f'Created: {created}'))
        self.stdout.write(self.style.WARNING(f'Skipped (already present): {skipped}'))
