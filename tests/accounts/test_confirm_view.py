from django.contrib.sessions.models import Session
from django.test import TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.tokens import password_change_token
from tests.accounts.factories import make_user


def confirm_url(user, token=None):
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = token or password_change_token.make_token(user)
    return reverse('accounts:password_change_confirm', kwargs={'uidb64': uidb64, 'token': token})


class PasswordChangeConfirmTests(TestCase):
    def setUp(self):
        self.user = make_user(password='OldPass123!')

    def test_valid_token_get_renders_set_password_form(self):
        self.client.force_login(self.user)
        resp = self.client.get(confirm_url(self.user))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'new_password1')

    def test_invalid_token_renders_invalid_page(self):
        self.client.force_login(self.user)
        resp = self.client.get(confirm_url(self.user, token='bad-token'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'tidak valid')

    def test_other_users_link_is_rejected(self):
        other = make_user(email='other@example.com')
        self.client.force_login(self.user)
        resp = self.client.get(confirm_url(other))
        self.assertContains(resp, 'tidak valid')

    def test_post_sets_password_revokes_sessions_and_logs_out(self):
        # Two devices logged in.
        self.client.force_login(self.user)
        other_device = self.client_class()
        other_device.force_login(self.user)
        self.assertEqual(Session.objects.count(), 2)

        resp = self.client.post(confirm_url(self.user), {
            'new_password1': 'BrandNewPass456!',
            'new_password2': 'BrandNewPass456!',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('BrandNewPass456!'))
        # All sessions revoked (both devices).
        self.assertEqual(Session.objects.count(), 0)

    def test_weak_password_rejected(self):
        self.client.force_login(self.user)
        resp = self.client.post(confirm_url(self.user), {
            'new_password1': '123',
            'new_password2': '123',
        })
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('OldPass123!'))
