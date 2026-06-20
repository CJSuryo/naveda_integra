# tests/customers/test_views.py
import json
import urllib.parse
from django.test import TestCase, Client
from django.urls import reverse
from .factories import make_user, make_eb, make_eb_lv2, make_customer


class CustomerListViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user()
        self.client.force_login(self.user)

    def test_list_returns_200(self):
        response = self.client.get(reverse('customers:list'))
        self.assertEqual(response.status_code, 200)

    def test_list_shows_customers(self):
        eb = make_eb()
        make_customer(eb=eb, nama='Andi Wijaya')
        response = self.client.get(reverse('customers:list'))
        self.assertContains(response, 'Andi Wijaya')

    def test_list_search_filters_by_nama(self):
        eb = make_eb()
        make_customer(eb=eb, nama='Cari Ini')
        make_customer(eb=eb, nama='Bukan Ini')
        response = self.client.get(reverse('customers:list'), {'q': 'Cari'})
        self.assertContains(response, 'Cari Ini')
        self.assertNotContains(response, 'Bukan Ini')

    def test_list_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('customers:list'))
        self.assertNotEqual(response.status_code, 200)


class CustomerCreateViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user()
        self.client.force_login(self.user)
        self.eb = make_eb()

    def test_create_get_returns_200(self):
        response = self.client.get(reverse('customers:create'))
        self.assertEqual(response.status_code, 200)

    def test_create_post_creates_customer(self):
        from apps.customers.models import Customer
        self.client.post(reverse('customers:create'), {
            'nama': 'Pelanggan Baru',
            'email': 'baru@test.com',
            'eb_selection': f'lv1:{self.eb.pk}',
        })
        self.assertTrue(Customer.objects.filter(nama='Pelanggan Baru').exists())

    def test_create_post_resolves_lv2_selection(self):
        from apps.customers.models import Customer
        from .factories import make_eb_lv2
        lv2 = make_eb_lv2(eb=self.eb)
        self.client.post(reverse('customers:create'), {
            'nama': 'Lv2 Customer',
            'eb_selection': f'lv2:{lv2.pk}',
        })
        c = Customer.objects.get(nama='Lv2 Customer')
        self.assertEqual(c.entitas_bisnis, self.eb)
        self.assertEqual(c.entitas_bisnis_lv2, lv2)
        self.assertIsNone(c.entitas_bisnis_lv3)

    def test_create_post_missing_eb_shows_error(self):
        response = self.client.post(reverse('customers:create'), {
            'nama': 'No EB',
            'eb_selection': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], None, 'Pilih entitas bisnis.')


class CustomerQuickCreateViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user()
        self.client.force_login(self.user)
        self.eb = make_eb()

    def test_quick_create_returns_json_success(self):
        body = urllib.parse.urlencode({'nama': 'Quick Cust', 'eb_selection': f'lv1:{self.eb.pk}'})
        response = self.client.post(
            reverse('customers:quick_create'),
            body,
            content_type='application/x-www-form-urlencoded',
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertIn('id', data['customer'])
        self.assertEqual(data['customer']['nama'], 'Quick Cust')

    def test_quick_create_missing_nama_returns_error(self):
        body = urllib.parse.urlencode({'nama': '', 'eb_selection': f'lv1:{self.eb.pk}'})
        response = self.client.post(
            reverse('customers:quick_create'),
            body,
            content_type='application/x-www-form-urlencoded',
        )
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('nama', data['errors'])


class CustomerDeleteViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user()
        self.client.force_login(self.user)

    def test_delete_removes_customer(self):
        from apps.customers.models import Customer
        c = make_customer()
        self.client.post(reverse('customers:delete', args=[c.pk]))
        self.assertFalse(Customer.objects.filter(pk=c.pk).exists())
