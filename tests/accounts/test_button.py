from django.test import TestCase
from django.urls import reverse

from tests.accounts.factories import make_user


class ChangePasswordButtonTests(TestCase):
    def _give_user_update_perm(self, user):
        from apps.accounts.models import NiPermission
        perm, _ = NiPermission.objects.get_or_create(code='user_update', defaults={'name': 'Update User'})
        user.ni_permissions.add(perm)

    def test_button_shown_on_own_edit_page(self):
        user = make_user()
        self._give_user_update_perm(user)
        self.client.force_login(user)
        resp = self.client.get(reverse('accounts:user_update', args=[user.pk]))
        self.assertContains(resp, reverse('accounts:password_change_request'))

    def test_button_hidden_on_other_users_edit_page(self):
        user = make_user(email='editor@example.com')
        other = make_user(email='victim@example.com')
        self._give_user_update_perm(user)
        self.client.force_login(user)
        resp = self.client.get(reverse('accounts:user_update', args=[other.pk]))
        self.assertNotContains(resp, reverse('accounts:password_change_request'))
