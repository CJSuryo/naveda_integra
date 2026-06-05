from decimal import Decimal
from django.test import TestCase
from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3
from pos_config.models import MerchantPOSConfig, OutletPOSConfig


class OutletPOSConfigTests(TestCase):
    def setUp(self):
        tipe = TipeEntitas.objects.create(nama='FnB')
        self.eb = EntitasBisnis.objects.create(nama='Naveda Kopi', tipe_entitas=tipe)
        self.lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=self.eb, nama='Senopati Area')
        self.lv3 = EntitasBisnisLv3.objects.create(parent_lv2=self.lv2, nama='Outlet Senopati')
        self.merchant = MerchantPOSConfig.objects.create(
            entitas_bisnis=self.eb,
            default_tax_pct=Decimal('11.00'),
        )

    def test_outlet_config_creation(self):
        cfg = OutletPOSConfig.objects.create(
            entitas_bisnis_lv3=self.lv3,
            merchant_config=self.merchant,
        )
        self.assertEqual(str(cfg), f'Outlet POS Config — {self.lv3.nama}')
        self.assertIsNone(cfg.tax_pct)
        self.assertTrue(cfg.is_active)

    def test_one_to_one_constraint(self):
        OutletPOSConfig.objects.create(
            entitas_bisnis_lv3=self.lv3,
            merchant_config=self.merchant,
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            OutletPOSConfig.objects.create(
                entitas_bisnis_lv3=self.lv3,
                merchant_config=self.merchant,
            )
