from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models

ip_validator = RegexValidator(
    regex=r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$',
    message='Невірний формат IP-адреси',
)
mac_validator = RegexValidator(
    regex=r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$',
    message='Невірний формат MAC-адреси',
)


class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    ip_address = models.CharField(max_length=15, blank=True, null=True, validators=[ip_validator])
    last_status = models.BooleanField(default=False)
    last_latency = models.FloatField(blank=True, null=True)
    last_checked = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Record(models.Model):
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='records')
    last_name = models.CharField(max_length=50)
    first_name = models.CharField(max_length=50)
    middle_name = models.CharField(max_length=50, blank=True, null=True)
    ip_address = models.CharField(max_length=15, unique=True, validators=[ip_validator])
    mac_address = models.CharField(max_length=17, unique=True, validators=[mac_validator])
    service = models.CharField(max_length=100)
    office = models.CharField(max_length=10)
    work_phone = models.CharField(max_length=20, blank=True, null=True)
    mobile_phone = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f'{self.last_name} {self.first_name}'

    @property
    def full_name(self):
        return ' '.join(p for p in [self.last_name, self.first_name, self.middle_name] if p)


class SupportRequest(models.Model):
    STATUS_CHOICES = [
        ('new', 'Новий'),
        ('in_progress', 'В процесі'),
        ('resolved', 'Виконано'),
    ]

    name = models.CharField(max_length=100)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='support_requests')
    email = models.EmailField(max_length=100)
    issue_type = models.CharField(max_length=50)
    description = models.TextField()
    urgency = models.CharField(max_length=20)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    admin_response = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['status', '-created_at']

    def __str__(self):
        return f'#{self.pk} {self.issue_type}'


class KnowledgeBaseArticle(models.Model):
    title = models.CharField(max_length=200, db_index=True)
    content = models.TextField()
    category = models.CharField(max_length=50, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'title']

    def __str__(self):
        return self.title


class DownloadLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    filename = models.CharField(max_length=100)
    downloaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-downloaded_at']

    def __str__(self):
        return f'{self.filename} @ {self.downloaded_at:%Y-%m-%d %H:%M}'
