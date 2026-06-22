from django.test import TestCase

from apps.accounts.forms import UserForm, NamedSetPasswordForm, CurrentPasswordForm
from tests.accounts.factories import make_user


class UserFormTests(TestCase):
    def test_userform_has_no_password_field(self):
        form = UserForm()
        self.assertNotIn('password', form.fields)


class CurrentPasswordFormTests(TestCase):
    def test_accepts_correct_password(self):
        user = make_user(password='OldPass123!')
        form = CurrentPasswordForm(user=user, data={'current_password': 'OldPass123!'})
        self.assertTrue(form.is_valid())

    def test_rejects_wrong_password(self):
        user = make_user(password='OldPass123!')
        form = CurrentPasswordForm(user=user, data={'current_password': 'wrong'})
        self.assertFalse(form.is_valid())


class NamedSetPasswordFormTests(TestCase):
    def test_widgets_have_ni_input_class(self):
        user = make_user()
        form = NamedSetPasswordForm(user)
        self.assertIn('ni-input', form.fields['new_password1'].widget.attrs.get('class', ''))
