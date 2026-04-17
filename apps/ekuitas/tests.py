"""Tests for apps.ekuitas."""
import json
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.master_data.models import Akun

from .models import ModalDisetor, ModalDisetorDebit, Pemilik
from .services import (
    create_modal_disetor,
    delete_modal_disetor,
    get_or_create_pemilik,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_eb(nama='Test EB'):
    tipe, _ = TipeEntitas.objects.get_or_create(nama='PT')
    return EntitasBisnis.objects.create(nama=nama, tipe_entitas=tipe, status_aktif=True)


def _make_accounts():
    """Create minimal Akun records needed for ekuitas service tests."""
    modal_akun, _ = Akun.objects.get_or_create(
        kode_akun='3.1.1.1',
        defaults={'nama': 'Modal Disetor', 'kategori_id': 'ekuitas'},
    )
    kas_akun, _ = Akun.objects.get_or_create(
        kode_akun='1.1.1.1',
        defaults={'nama': 'Kas Utama', 'kategori_id': 'aset'},
    )
    return modal_akun, kas_akun


# ── Model Tests ───────────────────────────────────────────────────────────────

class PemilikModelTests(TestCase):
    def test_str(self):
        p = Pemilik.objects.create(nama='Budi Santoso')
        self.assertEqual(str(p), 'Budi Santoso')

    def test_nama_unique(self):
        Pemilik.objects.create(nama='Unique Name')
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Pemilik.objects.create(nama='Unique Name')


class ModalDisetorModelTests(TestCase):
    def setUp(self):
        self.eb = _make_eb()
        self.pemilik = Pemilik.objects.create(nama='Siti Rahayu')

    def test_str(self):
        md = ModalDisetor.objects.create(
            entitas_bisnis=self.eb,
            pemilik=self.pemilik,
            jumlah_modal=Decimal('100000000'),
            tanggal_setor='2024-01-01',
        )
        self.assertIn('Siti Rahayu', str(md))

    def test_cascade_delete_debit_lines(self):
        _, kas = _make_accounts()
        md = ModalDisetor.objects.create(
            entitas_bisnis=self.eb,
            pemilik=self.pemilik,
            jumlah_modal=Decimal('50000000'),
            tanggal_setor='2024-01-01',
        )
        ModalDisetorDebit.objects.create(modal_disetor=md, akun=kas, jumlah=Decimal('50000000'))
        self.assertEqual(md.debit_lines.count(), 1)
        md.delete()
        self.assertEqual(ModalDisetorDebit.objects.filter(modal_disetor_id=md.pk).count(), 0)


# ── Service Tests ─────────────────────────────────────────────────────────────

class GetOrCreatePemilikTests(TestCase):
    def test_creates_new(self):
        p = get_or_create_pemilik('Ahmad Yani')
        self.assertEqual(p.nama, 'Ahmad Yani')
        self.assertEqual(Pemilik.objects.count(), 1)

    def test_case_insensitive_lookup(self):
        Pemilik.objects.create(nama='Ahmad Yani')
        p = get_or_create_pemilik('ahmad yani')
        self.assertEqual(Pemilik.objects.count(), 1)
        self.assertEqual(p.nama, 'Ahmad Yani')


class CreateModalDisetorServiceTests(TestCase):
    def setUp(self):
        self.eb = _make_eb()
        self.pemilik = Pemilik.objects.create(nama='Adi Wijaya')
        self.modal_akun, self.kas_akun = _make_accounts()

    def test_creates_record_and_journal(self):
        record = create_modal_disetor(
            entitas_bisnis_id=self.eb.pk,
            pemilik_id=self.pemilik.pk,
            tanggal='2024-06-01',
            jumlah_modal=Decimal('100000000'),
            keterangan='Setoran awal',
            debit_lines=[{'akun_id': self.kas_akun.pk, 'jumlah': '100000000'}],
        )
        self.assertIsNotNone(record.pk)
        self.assertIsNotNone(record.jurnal_header)
        self.assertEqual(record.pemilik, self.pemilik)
        self.assertEqual(record.jumlah_modal, Decimal('100000000'))

    def test_journal_has_correct_entries(self):
        record = create_modal_disetor(
            entitas_bisnis_id=self.eb.pk,
            pemilik_id=self.pemilik.pk,
            tanggal='2024-06-01',
            jumlah_modal=Decimal('50000000'),
            keterangan='',
            debit_lines=[{'akun_id': self.kas_akun.pk, 'jumlah': '50000000'}],
        )
        details = list(record.jurnal_header.details.all())
        self.assertEqual(len(details), 2)
        total_debit = sum(d.debit for d in details)
        total_kredit = sum(d.kredit for d in details)
        self.assertEqual(total_debit, Decimal('50000000'))
        self.assertEqual(total_kredit, Decimal('50000000'))

    def test_debit_lines_saved(self):
        record = create_modal_disetor(
            entitas_bisnis_id=self.eb.pk,
            pemilik_id=self.pemilik.pk,
            tanggal='2024-06-01',
            jumlah_modal=Decimal('80000000'),
            keterangan='',
            debit_lines=[{'akun_id': self.kas_akun.pk, 'jumlah': '80000000'}],
        )
        self.assertEqual(record.debit_lines.count(), 1)

    def test_sum_mismatch_raises(self):
        with self.assertRaises(ValueError):
            create_modal_disetor(
                entitas_bisnis_id=self.eb.pk,
                pemilik_id=self.pemilik.pk,
                tanggal='2024-06-01',
                jumlah_modal=Decimal('100000000'),
                keterangan='',
                debit_lines=[{'akun_id': self.kas_akun.pk, 'jumlah': '50000000'}],
            )

    def test_empty_debit_lines_raises(self):
        with self.assertRaises(ValueError):
            create_modal_disetor(
                entitas_bisnis_id=self.eb.pk,
                pemilik_id=self.pemilik.pk,
                tanggal='2024-06-01',
                jumlah_modal=Decimal('100000000'),
                keterangan='',
                debit_lines=[],
            )

    def test_sequential_journal_numbers(self):
        r1 = create_modal_disetor(
            entitas_bisnis_id=self.eb.pk, pemilik_id=self.pemilik.pk,
            tanggal='2024-06-01', jumlah_modal=Decimal('10000000'), keterangan='',
            debit_lines=[{'akun_id': self.kas_akun.pk, 'jumlah': '10000000'}],
        )
        r2 = create_modal_disetor(
            entitas_bisnis_id=self.eb.pk, pemilik_id=self.pemilik.pk,
            tanggal='2024-06-02', jumlah_modal=Decimal('20000000'), keterangan='',
            debit_lines=[{'akun_id': self.kas_akun.pk, 'jumlah': '20000000'}],
        )
        self.assertEqual(r1.jurnal_header.nomor_transaksi, 'TRX-MD-001')
        self.assertEqual(r2.jurnal_header.nomor_transaksi, 'TRX-MD-002')


class DeleteModalDisetorServiceTests(TestCase):
    def setUp(self):
        self.eb = _make_eb()
        self.pemilik = Pemilik.objects.create(nama='Benny Cahyono')
        self.modal_akun, self.kas_akun = _make_accounts()

    def _make_record(self):
        return create_modal_disetor(
            entitas_bisnis_id=self.eb.pk,
            pemilik_id=self.pemilik.pk,
            tanggal='2024-07-01',
            jumlah_modal=Decimal('30000000'),
            keterangan='',
            debit_lines=[{'akun_id': self.kas_akun.pk, 'jumlah': '30000000'}],
        )

    def test_delete_removes_record_and_journal(self):
        from apps.jurnal.models import JurnalHeader
        record = self._make_record()
        header_pk = record.jurnal_header.pk
        delete_modal_disetor(record)
        self.assertFalse(ModalDisetor.objects.filter(pk=record.pk).exists())
        self.assertFalse(JurnalHeader.objects.filter(pk=header_pk).exists())

    def test_delete_saldo_awal_keeps_journal(self):
        from apps.jurnal.models import JurnalHeader
        record = self._make_record()
        header = record.jurnal_header
        header.is_saldo_awal = True
        header.save(update_fields=['is_saldo_awal'])
        delete_modal_disetor(record)
        self.assertFalse(ModalDisetor.objects.filter(pk=record.pk).exists())
        self.assertTrue(JurnalHeader.objects.filter(pk=header.pk).exists())


# ── View Tests ────────────────────────────────────────────────────────────────

class EkuitasViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@naveda.id', password='testpassword123'
        )
        self.client.force_login(self.user)
        self.eb = _make_eb()
        self.pemilik = Pemilik.objects.create(nama='Pemilik View Test')
        self.modal_akun, self.kas_akun = _make_accounts()

    def _make_md(self):
        return create_modal_disetor(
            entitas_bisnis_id=self.eb.pk,
            pemilik_id=self.pemilik.pk,
            tanggal='2024-08-01',
            jumlah_modal=Decimal('75000000'),
            keterangan='Test view',
            debit_lines=[{'akun_id': self.kas_akun.pk, 'jumlah': '75000000'}],
        )

    # List
    def test_list_requires_login(self):
        self.client.logout()
        r = self.client.get(reverse('ekuitas:list'))
        self.assertRedirects(r, f'/accounts/login/?next={reverse("ekuitas:list")}')

    def test_list_ok(self):
        r = self.client.get(reverse('ekuitas:list'))
        self.assertEqual(r.status_code, 200)

    def test_list_filtered(self):
        self._make_md()
        r = self.client.get(reverse('ekuitas:list'), {'entitas_bisnis': self.eb.pk})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context['records']), 1)

    # History
    def test_history_ok(self):
        r = self.client.get(reverse('ekuitas:history'))
        self.assertEqual(r.status_code, 200)

    def test_history_filtered(self):
        self._make_md()
        r = self.client.get(reverse('ekuitas:history'), {
            'entitas_bisnis': self.eb.pk,
            'tanggal_sampai': '2024-12-31',
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context['records']), 1)

    # Detail
    def test_detail_ok(self):
        md = self._make_md()
        r = self.client.get(reverse('ekuitas:detail', args=[md.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['record'], md)

    def test_detail_404_for_missing(self):
        r = self.client.get(reverse('ekuitas:detail', args=[999999]))
        self.assertEqual(r.status_code, 404)

    # Create GET
    def test_create_get(self):
        r = self.client.get(reverse('ekuitas:create'))
        self.assertEqual(r.status_code, 200)

    # Create POST — happy path
    def test_create_post_valid(self):
        debit_lines = json.dumps([{'akun_id': self.kas_akun.pk, 'jumlah': 20000000}])
        r = self.client.post(reverse('ekuitas:create'), {
            'entitas_bisnis': self.eb.pk,
            'pemilik': self.pemilik.pk,
            'tanggal': '2024-09-01',
            'keterangan': '',
            'debit_lines_json': debit_lines,
        })
        self.assertEqual(ModalDisetor.objects.count(), 1)
        record = ModalDisetor.objects.first()
        self.assertRedirects(r, reverse('ekuitas:detail', args=[record.pk]))

    # Create POST — validation errors
    def test_create_post_missing_fields(self):
        r = self.client.post(reverse('ekuitas:create'), {})
        self.assertEqual(r.status_code, 200)
        self.assertIn('errors', r.context)
        self.assertTrue(len(r.context['errors']) > 0)

    # Delete GET
    def test_delete_get(self):
        md = self._make_md()
        r = self.client.get(reverse('ekuitas:delete', args=[md.pk]))
        self.assertEqual(r.status_code, 200)

    # Delete POST
    def test_delete_post(self):
        md = self._make_md()
        r = self.client.post(reverse('ekuitas:delete', args=[md.pk]))
        self.assertRedirects(r, reverse('ekuitas:list'))
        self.assertFalse(ModalDisetor.objects.filter(pk=md.pk).exists())

    # API — pemilik search
    def test_api_pemilik_search(self):
        r = self.client.get(reverse('ekuitas:api_pemilik_search'), {'term': 'Pemilik'})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIsInstance(data, list)
        self.assertEqual(data[0]['text'], 'Pemilik View Test')

    # API — pemilik create
    def test_api_pemilik_create_ok(self):
        r = self.client.post(reverse('ekuitas:api_pemilik_create'), {'nama': 'Baru Sekali'})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn('id', data)
        self.assertTrue(Pemilik.objects.filter(nama='Baru Sekali').exists())

    def test_api_pemilik_create_duplicate(self):
        """Duplicate name returns the existing pemilik (not an error)."""
        existing = Pemilik.objects.create(nama='Sudah Ada')
        r = self.client.post(reverse('ekuitas:api_pemilik_create'), {'nama': 'Sudah Ada'})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data['id'], existing.pk)
        self.assertEqual(data['text'], 'Sudah Ada')
