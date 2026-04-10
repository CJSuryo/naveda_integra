"""Unit tests for the accounts app."""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


class UserModelTests(TestCase):
    def test_create_user(self):
        user = User.objects.create_user(email='test@example.com', password='pass1234', name='Test User')
        self.assertEqual(user.email, 'test@example.com')
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_create_superuser(self):
        su = User.objects.create_superuser(email='admin@example.com', password='admin1234', name='Admin')
        self.assertTrue(su.is_staff)
        self.assertTrue(su.is_superuser)

    def test_create_user_without_email_raises(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email='', password='pass1234', name='No Email')

    def test_user_str(self):
        user = User.objects.create_user(email='str@example.com', password='pass', name='Str Test')
        self.assertEqual(str(user), 'str@example.com')

    def test_email_is_username_field(self):
        self.assertEqual(User.USERNAME_FIELD, 'email')


class LoginViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email='login@example.com', password='pass1234', name='Login User')
        self.url = reverse('accounts:login')

    def test_login_page_get(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/login.html')

    def test_login_success(self):
        response = self.client.post(self.url, {'username': 'login@example.com', 'password': 'pass1234'})
        self.assertRedirects(response, reverse('home'))

    def test_login_with_safe_next(self):
        next_url = reverse('entitas_bisnis:list')
        response = self.client.post(
            f'{self.url}?next={next_url}',
            {'username': 'login@example.com', 'password': 'pass1234'},
        )
        self.assertRedirects(response, next_url)

    def test_login_with_unsafe_next_redirects_home(self):
        response = self.client.post(
            f'{self.url}?next=http://evil.com/steal',
            {'username': 'login@example.com', 'password': 'pass1234'},
        )
        self.assertRedirects(response, reverse('home'))

    def test_login_wrong_password(self):
        response = self.client.post(self.url, {'username': 'login@example.com', 'password': 'wrong'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['user'].is_authenticated)

    def test_authenticated_user_redirected(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse('home'))


class RegisterViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse('accounts:register')

    def test_register_page_get(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/register.html')

    def test_register_success(self):
        data = {
            'email': 'new@example.com',
            'name': 'New User',
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
        }
        response = self.client.post(self.url, data)
        self.assertRedirects(response, reverse('home'))
        self.assertTrue(User.objects.filter(email='new@example.com').exists())

    def test_register_password_mismatch(self):
        data = {
            'email': 'mismatch@example.com',
            'name': 'Mismatch User',
            'password1': 'pass1234',
            'password2': 'wrong',
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email='mismatch@example.com').exists())


class LogoutViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email='logout@example.com', password='pass1234', name='Logout User')

    def test_logout(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('accounts:logout'))
        self.assertRedirects(response, reverse('accounts:login'))

    def test_home_requires_login(self):
        response = self.client.get(reverse('home'))
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('home')}")
