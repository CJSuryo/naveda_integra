# tests/customers/test_models.py
import datetime
from django.test import TestCase
from apps.customers.models import Customer


class CustomerUmurTest(TestCase):
    def test_umur_computed_from_tanggal_lahir(self):
        today = datetime.date.today()
        born = today.replace(year=today.year - 30)
        c = Customer(tanggal_lahir=born)
        self.assertEqual(c.umur, 30)

    def test_umur_none_when_no_tanggal_lahir(self):
        c = Customer()
        self.assertIsNone(c.umur)

    def test_umur_birthday_not_yet_this_year(self):
        today = datetime.date.today()
        born = datetime.date(today.year - 1, today.month, today.day)
        c = Customer(tanggal_lahir=born)
        self.assertEqual(c.umur, 1)


class CustomerStrTest(TestCase):
    def test_str_returns_nama(self):
        c = Customer(nama='Budi Santoso')
        self.assertEqual(str(c), 'Budi Santoso')
