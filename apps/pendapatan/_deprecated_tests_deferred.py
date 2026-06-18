from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.master_data.models import Akun
from apps.purchase.models import SubTransactionType

from .models import (
    PendapatanHeader, PendapatanEntitasBisnis, PendapatanItem,
    DeferredRevenueSchedule, DeferredRevenueEntry,
)
from .deferred_services import create_deferred_schedule, recognize_deferred_entry


def make_deferred_item():
    tipe = TipeEntitas.objects.create(nama='Penyewa')
    eb = EntitasBisnis.objects.create(nama='PT X', tipe_entitas=tipe, relasi='pelanggan')
    coa_kas = Akun.objects.create(kategori_id='aset', nama='Kas', kode_akun='1.1.1')
    coa_revenue = Akun.objects.create(kategori_id='pendapatan', nama='Pendapatan Sewa', kode_akun='4.1.1')
    coa_deferred = Akun.objects.create(kategori_id='kewajiban', nama='Pendapatan Diterima di Muka', kode_akun='2.5.1')
    stt = SubTransactionType.objects.create(
        nama='Sewa', module='pendapatan', direction='inflow', default_offset_account=coa_revenue,
    )
    header = PendapatanHeader.objects.create(tanggal=date(2026, 1, 1), payment_type='cash', status='draft')
    eb_group = PendapatanEntitasBisnis.objects.create(
        pendapatan_header=header, entitas_bisnis=eb, payment_account=coa_kas,
    )
    item = PendapatanItem.objects.create(
        pendapatan_eb=eb_group,
        deskripsi_item='Sewa 3 bulan',
        kategori='sewa',
        sub_transaction_type=stt,
        jumlah_bruto=Decimal('3000000'),
        revenue_account=coa_revenue,
        payment_account=coa_kas,
        is_deferred=True,
        deferred_account=coa_deferred,
        recognition_account=coa_revenue,
        deferred_tanggal_mulai=date(2026, 1, 1),
        deferred_tanggal_selesai=date(2026, 3, 31),
        deferred_metode='straight_line',
    )
    return item, coa_deferred, coa_revenue


class CreateDeferredScheduleTests(TestCase):
    def setUp(self):
        self.item, self.coa_deferred, self.coa_revenue = make_deferred_item()

    def test_creates_schedule(self):
        schedule = create_deferred_schedule(self.item)
        self.assertIsNotNone(schedule.pk)
        self.assertEqual(schedule.jumlah_total, Decimal('3000000'))

    def test_creates_3_entries_for_3_months(self):
        schedule = create_deferred_schedule(self.item)
        self.assertEqual(schedule.entries.count(), 3)

    def test_straight_line_equal_amounts(self):
        schedule = create_deferred_schedule(self.item)
        amounts = list(schedule.entries.order_by('periode').values_list('jumlah', flat=True))
        self.assertEqual(len(set(amounts)), 1)

    def test_total_entries_equal_jumlah_total(self):
        schedule = create_deferred_schedule(self.item)
        total = sum(schedule.entries.values_list('jumlah', flat=True))
        self.assertEqual(total, Decimal('3000000'))

    def test_all_entries_pending(self):
        schedule = create_deferred_schedule(self.item)
        self.assertEqual(schedule.entries.filter(status='pending').count(), 3)

    def test_periode_keys_are_first_of_month(self):
        schedule = create_deferred_schedule(self.item)
        periodes = list(schedule.entries.values_list('periode', flat=True).order_by('periode'))
        self.assertEqual(periodes[0].day, 1)
        self.assertEqual(periodes[0].month, 1)
        self.assertEqual(periodes[1].month, 2)
        self.assertEqual(periodes[2].month, 3)


class RecognizeDeferredEntryTests(TestCase):
    def setUp(self):
        self.item, self.coa_deferred, self.coa_revenue = make_deferred_item()
        self.schedule = create_deferred_schedule(self.item)
        self.entry = self.schedule.entries.order_by('periode').first()

    def test_entry_status_becomes_recognized(self):
        recognize_deferred_entry(self.entry)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, 'recognized')

    def test_generates_journal(self):
        recognize_deferred_entry(self.entry)
        self.entry.refresh_from_db()
        self.assertIsNotNone(self.entry.jurnal_header)

    def test_journal_dr_deferred_cr_recognition(self):
        recognize_deferred_entry(self.entry)
        self.entry.refresh_from_db()
        details = self.entry.jurnal_header.details.all()
        dr = next(d for d in details if d.debit > 0)
        cr = next(d for d in details if d.kredit > 0)
        self.assertEqual(dr.akun, self.coa_deferred)
        self.assertEqual(cr.akun, self.coa_revenue)

    def test_raises_if_already_recognized(self):
        recognize_deferred_entry(self.entry)
        self.entry.refresh_from_db()
        with self.assertRaises(ValueError):
            recognize_deferred_entry(self.entry)
