"""Tests Fase 6 — transaksi & kontrol stok."""
from decimal import Decimal
from django.test import TestCase

from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
from apps.purchase.models import ItemMasterPurchase
from apps.inventory.models import StockMovement
from apps.inventory import ledger


class MovementTypeChoicesTests(TestCase):
    def test_new_movement_types_registered(self):
        codes = {c for c, _ in StockMovement.MOVEMENT_TYPE_CHOICES}
        for expected in {
            'adjustment_in', 'adjustment_out', 'opname_in', 'opname_out',
            'transfer_in', 'transfer_out', 'return_customer', 'return_supplier',
        }:
            self.assertIn(expected, codes)


class ReversalSetTests(TestCase):
    def test_outflow_set_includes_fase6(self):
        for t in {'adjustment_out', 'opname_out', 'transfer_out', 'return_supplier'}:
            self.assertIn(t, ledger.OUTFLOW_MOVEMENT_TYPES)

    def test_inflow_set_includes_fase6(self):
        for t in {'adjustment_in', 'opname_in', 'transfer_in', 'return_customer'}:
            self.assertIn(t, ledger.INFLOW_MOVEMENT_TYPES)
