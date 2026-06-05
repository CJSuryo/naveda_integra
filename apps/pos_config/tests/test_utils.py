from decimal import Decimal
from django.test import TestCase
from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3
from pos_config.models import MerchantPOSConfig, StorePOSConfig, OutletPOSConfig
from pos_config.utils import resolve_pos_config


class ResolvePOSConfigTests(TestCase):
    def setUp(self):
        tipe = TipeEntitas.objects.create(nama='FnB')
        self.eb = EntitasBisnis.objects.create(nama='Naveda', tipe_entitas=tipe)
        self.lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=self.eb, nama='Area')
        self.lv3 = EntitasBisnisLv3.objects.create(parent_lv2=self.lv2, nama='Outlet')
        self.merchant = MerchantPOSConfig.objects.create(
            entitas_bisnis=self.eb,
            default_tax_pct=Decimal('11.00'),
        )

    def test_returns_merchant_defaults_when_no_overrides(self):
        lv3 = EntitasBisnisLv3.objects.select_related(
            'parent_lv2__entitas_bisnis',
            'parent_lv2__pos_config',
        ).get(pk=self.lv3.pk)
        cfg = resolve_pos_config(lv3)
        self.assertIsNone(cfg['sub_transaction_type_id'])
        self.assertEqual(cfg['tax_pct'], Decimal('11.00'))

    def test_store_tax_overrides_merchant(self):
        StorePOSConfig.objects.create(
            entitas_bisnis_lv2=self.lv2,
            merchant_config=self.merchant,
            tax_pct=Decimal('5.00'),
        )
        lv3 = EntitasBisnisLv3.objects.select_related(
            'parent_lv2__entitas_bisnis',
            'parent_lv2__pos_config',
        ).get(pk=self.lv3.pk)
        cfg = resolve_pos_config(lv3)
        self.assertEqual(cfg['tax_pct'], Decimal('5.00'))

    def test_outlet_tax_overrides_store(self):
        StorePOSConfig.objects.create(
            entitas_bisnis_lv2=self.lv2,
            merchant_config=self.merchant,
            tax_pct=Decimal('5.00'),
        )
        OutletPOSConfig.objects.create(
            entitas_bisnis_lv3=self.lv3,
            merchant_config=self.merchant,
            tax_pct=Decimal('0.00'),
        )
        lv3 = EntitasBisnisLv3.objects.select_related(
            'parent_lv2__entitas_bisnis',
            'parent_lv2__pos_config',
            'pos_config',
        ).get(pk=self.lv3.pk)
        cfg = resolve_pos_config(lv3)
        self.assertEqual(cfg['tax_pct'], Decimal('0.00'))

    def test_no_config_returns_zero_tax(self):
        eb2 = EntitasBisnis.objects.create(nama='Other', tipe_entitas=TipeEntitas.objects.first())
        lv2b = EntitasBisnisLv2.objects.create(entitas_bisnis=eb2, nama='B')
        lv3b = EntitasBisnisLv3.objects.create(parent_lv2=lv2b, nama='C')
        lv3b = EntitasBisnisLv3.objects.select_related(
            'parent_lv2__entitas_bisnis', 'parent_lv2__pos_config',
        ).get(pk=lv3b.pk)
        cfg = resolve_pos_config(lv3b)
        self.assertEqual(cfg['tax_pct'], Decimal('0'))
