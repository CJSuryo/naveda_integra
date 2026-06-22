from django.core import mail
from django.test import RequestFactory, TestCase

from apps.accounts.emails import send_password_change_email
from tests.accounts.factories import make_user


class SendPasswordChangeEmailTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_sends_one_email_to_user(self):
        user = make_user(email='target@example.com')
        request = self.factory.get('/accounts/password-change/request/')
        send_password_change_email(request, user)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['target@example.com'])

    def test_email_has_html_alternative_and_inline_logo(self):
        user = make_user(email='target@example.com')
        request = self.factory.get('/accounts/password-change/request/')
        send_password_change_email(request, user)
        msg = mail.outbox[0]
        # one text/html alternative
        self.assertTrue(any(ct == 'text/html' for _, ct in msg.alternatives))
        # attachments are MIMEImage objects (Message subclass) with Content-ID <logo>
        has_logo = any(part.get('Content-ID') == '<logo>' for part in msg.attachments)
        self.assertTrue(has_logo)

    def test_email_contains_absolute_link(self):
        user = make_user(email='target@example.com')
        request = self.factory.get('/accounts/password-change/request/')
        send_password_change_email(request, user)
        body = mail.outbox[0].body
        self.assertIn('http', body)
        self.assertIn('/password-change/', body)
