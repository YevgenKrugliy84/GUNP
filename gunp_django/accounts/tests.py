from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class RegistrationTests(TestCase):
    def test_register_creates_user_and_logs_in(self):
        response = self.client.post(reverse('accounts:register'), {
            'username': 'newuser',
            'password1': 'a-very-strong-pass123',
            'password2': 'a-very-strong-pass123',
            'department': 'Тестовий підрозділ',
        })
        self.assertRedirects(response, reverse('directory:index'))
        self.assertTrue(User.objects.filter(username='newuser').exists())
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_register_rejects_duplicate_username(self):
        User.objects.create_user(username='taken', password='whatever123')
        response = self.client.post(reverse('accounts:register'), {
            'username': 'taken',
            'password1': 'a-very-strong-pass123',
            'password2': 'a-very-strong-pass123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(username='taken').count(), 1)


class LoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='loginuser', password='correct-pass123')

    def test_login_with_correct_credentials_redirects_to_index(self):
        response = self.client.post(reverse('accounts:login'), {
            'username': 'loginuser', 'password': 'correct-pass123',
        })
        self.assertRedirects(response, reverse('directory:index'))

    def test_login_with_wrong_password_does_not_authenticate(self):
        response = self.client.post(reverse('accounts:login'), {
            'username': 'loginuser', 'password': 'wrong-password',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_logout_redirects_to_index(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('accounts:logout'))
        self.assertRedirects(response, reverse('directory:index'))
