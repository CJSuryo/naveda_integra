"""Unit tests for the piutang app."""
from django.test import TestCase
from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
from .models import PiutangHeader, PiutangDetail


class PiutangModelTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)

    def test_piutang_header_str(self):
        h = PiutangHeader.objects.create(entitas_bisnis=self.entitas)
        self.assertIn(str(h.id), str(h))

    def test_piutang_detail_str(self):
        h = PiutangHeader.objects.create(entitas_bisnis=self.entitas)
        d = PiutangDetail.objects.create(piutang_header=h)
        self.assertIn(str(h.id), str(d))

    def test_cascade_delete(self):
        h = PiutangHeader.objects.create(entitas_bisnis=self.entitas)
        PiutangDetail.objects.create(piutang_header=h)
        h.delete()
        self.assertEqual(PiutangDetail.objects.count(), 0)
