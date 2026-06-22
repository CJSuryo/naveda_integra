from django.conf import settings
from django.test import TestCase


class EmailSettingsTests(TestCase):
    def test_password_reset_timeout_is_15_minutes(self):
        self.assertEqual(settings.PASSWORD_RESET_TIMEOUT, 900)

    def test_default_from_email_configured(self):
        self.assertTrue(settings.DEFAULT_FROM_EMAIL)

    def test_email_host_is_gmail(self):
        self.assertEqual(settings.EMAIL_HOST, 'smtp.gmail.com')
