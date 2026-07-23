from django.test import TestCase, Client
from django.urls import reverse

from apps.accounts.models import User, Role, UserEntitasBisnis

from .factories import make_lv1, make_lv2, make_lv3, make_merchant, make_store


class MerchantConfigViewTest(TestCase):
    def setUp(self):
        role = Role.objects.create(kode='admin', nama='Admin', deskripsi='')
        self.user = User.objects.create_user(
            email='admin@test.com', password='pass', name='Admin', role=role
        )
        role_kasir = Role.objects.create(kode='kasir', nama='Kasir', deskripsi='')
        self.kasir = User.objects.create_user(
            email='kasir@test.com', password='pass', name='Kasir', role=role_kasir
        )
        self.lv1 = make_lv1()
        self.lv2 = make_lv2(self.lv1)
        self.client = Client()

    def _url(self):
        return reverse('pos_config:merchant_config', kwargs={'lv2_pk': self.lv2.pk})

    def test_config_view_requires_login(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    def test_config_view_forbidden_without_permission(self):
        self.client.force_login(self.kasir)
        self.assertEqual(self.client.get(self._url()).status_code, 403)

    def test_config_view_accessible_with_permission(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self._url()).status_code, 200)

    def test_config_view_creates_config_for_lv2(self):
        from pos_config.models import MerchantPOSConfig
        self.client.force_login(self.user)
        self.client.get(self._url())
        self.assertTrue(
            MerchantPOSConfig.objects.filter(entitas_bisnis_lv2=self.lv2).exists()
        )


class StoreScopingViewTest(TestCase):
    """A user must not reach another tenant's merchant through the URL."""

    def setUp(self):
        from apps.accounts.models import NiPermission
        # A non-admin role: admins bypass tenant scoping by design, so scoping
        # can only be exercised with a role that is granted the permission
        # explicitly.
        role = Role.objects.create(
            kode=Role.BUSINESS_OWNER, nama='Pemilik Bisnis', deskripsi=''
        )
        self.user = User.objects.create_user(
            email='a@test.com', password='pass', name='A', role=role
        )
        for code in ('pos_config_view', 'pos_config_manage'):
            perm, _ = NiPermission.objects.get_or_create(
                code=code, defaults={'name': code}
            )
            self.user.ni_permissions.add(perm)
        self.eb_a = make_lv1(nama='Grup A')
        self.eb_b = make_lv1(nama='Grup B')
        UserEntitasBisnis.objects.create(user=self.user, entitas_bisnis=self.eb_a)

        self.merchant_b = make_merchant(make_lv2(self.eb_b, nama='PT B'))
        self.client = Client()
        self.client.force_login(self.user)

    def test_store_list_of_foreign_merchant_is_404(self):
        url = reverse('pos_config:store_list', kwargs={'merchant_pk': self.merchant_b.pk})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_store_form_of_foreign_merchant_is_404(self):
        lv3_b = make_lv3(self.merchant_b.entitas_bisnis_lv2)
        url = reverse(
            'pos_config:store_form',
            kwargs={'merchant_pk': self.merchant_b.pk, 'lv3_pk': lv3_b.pk},
        )
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_payment_methods_of_foreign_store_is_404(self):
        store_b = make_store(self.merchant_b)
        url = reverse('pos_config:payment_method_list', kwargs={'store_pk': store_b.pk})
        self.assertEqual(self.client.get(url).status_code, 404)
