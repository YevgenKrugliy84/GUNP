from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Department, Record, SupportRequest

User = get_user_model()


class HealthzTests(TestCase):
    def test_healthz_returns_ok(self):
        response = self.client.get(reverse('healthz'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})


class IndexViewTests(TestCase):
    def test_index_loads_and_lists_departments(self):
        Department.objects.create(name='Тестовий підрозділ')
        response = self.client.get(reverse('directory:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Тестовий підрозділ')


class DepartmentDetailTests(TestCase):
    def setUp(self):
        self.department = Department.objects.create(name='Відділ Х')
        self.user = User.objects.create_user(username='someone', password='pass12345')

    def test_requires_login(self):
        response = self.client.get(reverse('directory:department', args=[self.department.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_logged_in_user_can_view(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('directory:department', args=[self.department.id]))
        self.assertEqual(response.status_code, 200)


class AddRecordPublicTests(TestCase):
    def setUp(self):
        self.department = Department.objects.create(name='Відділ Y')

    def test_creates_record_with_valid_data(self):
        response = self.client.post(reverse('directory:add_record_public', args=[self.department.id]), {
            'department': self.department.id,
            'last_name': 'Іванов',
            'first_name': 'Іван',
            'middle_name': '',
            'ip_address': '192.168.1.10',
            'mac_address': '00:14:22:01:23:45',
            'service': 'IT',
            'office': '101',
            'work_phone': '',
            'mobile_phone': '',
        })
        self.assertRedirects(response, reverse('directory:index'))
        self.assertTrue(Record.objects.filter(ip_address='192.168.1.10').exists())

    def test_rejects_invalid_ip(self):
        response = self.client.post(reverse('directory:add_record_public', args=[self.department.id]), {
            'department': self.department.id,
            'last_name': 'Іванов',
            'first_name': 'Іван',
            'ip_address': 'not-an-ip',
            'mac_address': '00:14:22:01:23:45',
            'service': 'IT',
            'office': '101',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Record.objects.filter(service='IT').exists())

    def test_rejects_duplicate_ip(self):
        Record.objects.create(
            department=self.department, last_name='Існуючий', first_name='Запис',
            ip_address='192.168.1.20', mac_address='00:14:22:01:23:46', service='IT', office='102',
        )
        response = self.client.post(reverse('directory:add_record_public', args=[self.department.id]), {
            'department': self.department.id,
            'last_name': 'Новий',
            'first_name': 'Дубль',
            'ip_address': '192.168.1.20',
            'mac_address': '00:14:22:01:23:47',
            'service': 'IT',
            'office': '103',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Record.objects.filter(ip_address='192.168.1.20').count(), 1)


class SupportRequestTests(TestCase):
    def setUp(self):
        self.department = Department.objects.create(name='Відділ Z')

    def test_submit_creates_request(self):
        response = self.client.post(reverse('directory:submit_support_request'), {
            'name': 'Петро Петренко',
            'department': self.department.id,
            'email': 'petro@example.com',
            'issue_type': 'network',
            'description': 'Не працює інтернет',
            'urgency': 'high',
        })
        self.assertRedirects(response, reverse('directory:tech_support'))
        self.assertTrue(SupportRequest.objects.filter(email='petro@example.com').exists())

    def test_check_support_request_finds_existing(self):
        req = SupportRequest.objects.create(
            name='Хтось', department=self.department, email='x@example.com',
            issue_type='software', description='Опис', urgency='low',
        )
        response = self.client.post(reverse('directory:check_support_request'), {'request_id': str(req.id)})
        self.assertContains(response, f'Заявка #{req.id}')

    def test_check_support_request_missing_shows_message(self):
        response = self.client.post(reverse('directory:check_support_request'), {'request_id': '999999'})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Заявка #999999')


class DepartmentStatusesTests(TestCase):
    def test_returns_cached_status_without_pinging(self):
        Department.objects.create(name='Онлайн відділ', ip_address='10.0.0.1', last_status=True, last_latency=12.5)
        response = self.client.get(reverse('directory:department_statuses'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['status'], 'online')
        self.assertEqual(data[0]['latency'], 12.5)
