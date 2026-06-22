from django.test import TestCase
from django.urls import reverse

from tests.accounts.factories import make_admin, make_user


class UserAdminChangeViewTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.client.force_login(self.admin)

    def test_change_view_loads_without_fielderror(self):
        target = make_user()
        url = reverse('admin:accounts_user_change', args=[target.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_change_view_shows_readonly_dates(self):
        target = make_user()
        url = reverse('admin:accounts_user_change', args=[target.pk])
        resp = self.client.get(url)
        # date_joined rendered as readonly text, not an editable input named date_joined
        self.assertNotContains(resp, 'name="date_joined"')
