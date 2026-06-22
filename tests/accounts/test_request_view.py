from django.core import mail
from django.test import TestCase
from django.urls import reverse

from tests.accounts.factories import make_user


class PasswordChangeRequestTests(TestCase):
    def setUp(self):
        self.user = make_user(password='OldPass123!')
        self.url = reverse('accounts:password_change_request')

    def test_requires_login(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

    def test_get_renders_current_password_form(self):
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'current_password')

    def test_wrong_current_password_sends_no_email(self):
        self.client.force_login(self.user)
        resp = self.client.post(self.url, {'current_password': 'wrong'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_correct_password_sends_email_and_shows_sent_page(self):
        self.client.force_login(self.user)
        resp = self.client.post(self.url, {'current_password': 'OldPass123!'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertContains(resp, 'Periksa email')
