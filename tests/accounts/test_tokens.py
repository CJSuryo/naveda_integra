from django.test import TestCase

from apps.accounts.tokens import password_change_token
from tests.accounts.factories import make_user


class PasswordChangeTokenTests(TestCase):
    def test_token_validates_for_same_user(self):
        user = make_user()
        token = password_change_token.make_token(user)
        self.assertTrue(password_change_token.check_token(user, token))

    def test_token_invalidated_after_password_change(self):
        user = make_user()
        token = password_change_token.make_token(user)
        user.set_password('BrandNewPass456!')
        user.save()
        self.assertFalse(password_change_token.check_token(user, token))

    def test_bad_token_rejected(self):
        user = make_user()
        self.assertFalse(password_change_token.check_token(user, 'not-a-real-token'))
