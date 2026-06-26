from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.master_data.models import Akun
from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.pendapatan.models import (
    KewajibabPelaksanaan,
    PendapatanEntitasBisnis,
    PendapatanHeader,
    PendapatanPiutangProfil,
    PIUTANG_PROFIL_FIELDS,
)
from apps.purchase.models import SubTransactionType


def _akun(kode, nama, kategori_id='aset'):
    return Akun.objects.create(kode_akun=kode, nama=nama, kategori_id=kategori_id)


class PendapatanPiutangProfilModelTest(TestCase):
    def test_profil_one_to_one_with_header(self):
        akun_piutang = _akun('1.1.4', 'Piutang Usaha')
        header = PendapatanHeader.objects.create(
            tanggal=date(2026, 1, 10), payment_type='credit', status='draft',
        )
        profil = PendapatanPiutangProfil.objects.create(
            pendapatan_header=header,
            debitur='PT Maju',
            coa_piutang_account=akun_piutang,
        )
        self.assertEqual(header.piutang_profil, profil)
        self.assertEqual(profil.debitur, 'PT Maju')
        # Constant lists the fields the modal mirrors from PiutangHeader.
        self.assertIn('coa_piutang_account', PIUTANG_PROFIL_FIELDS)
        self.assertIn('jatuh_tempo', PIUTANG_PROFIL_FIELDS)


class AdapterTest(TestCase):
    def _akun(self, kode, nama, kategori_id='aset'):
        return Akun.objects.create(kode_akun=kode, nama=nama, kategori_id=kategori_id)

    def _tipe_entitas(self):
        return TipeEntitas.objects.create(nama='Umum')

    def _stt(self):
        akun = self._akun('2.1.1', 'Offset')
        return SubTransactionType.objects.create(
            nama='Pendapatan Jasa', module='pendapatan', direction='inflow',
            default_offset_account=akun)

    def test_adapter_maps_profil_and_kp_items(self):
        akun_piutang = self._akun('1.1.4', 'Piutang Usaha')
        akun_pend = self._akun('4.1.1', 'Pendapatan Jasa', kategori_id='pendapatan')
        tipe = self._tipe_entitas()
        eb = EntitasBisnis.objects.create(nama='PT Alpha', standar_akuntansi='psak', tipe_entitas=tipe)
        header = PendapatanHeader.objects.create(
            tanggal=date(2026, 1, 10), payment_type='credit', status='draft')
        eb_group = PendapatanEntitasBisnis.objects.create(
            pendapatan_header=header, entitas_bisnis=eb)
        KewajibabPelaksanaan.objects.create(
            pendapatan_eb=eb_group, deskripsi_item='Jasa konsultasi', kategori='jasa',
            sub_transaction_type=self._stt(), nilai_kontrak=Decimal('2000'),
            revenue_account=akun_pend)
        PendapatanPiutangProfil.objects.create(
            pendapatan_header=header, debitur='PT Alpha',
            coa_piutang_account=akun_piutang, jenis_bunga='flat',
            suku_bunga=Decimal('10'))

        from apps.pendapatan.services import pendapatan_to_piutang_payload
        payload, details = pendapatan_to_piutang_payload(header)

        self.assertEqual(payload['debitur'], 'PT Alpha')
        self.assertEqual(payload['coa_piutang_account'], akun_piutang)
        self.assertEqual(payload['jenis_bunga'], 'flat')
        self.assertEqual(payload['tanggal'], header.tanggal)
        self.assertEqual(payload['entitas_bisnis'], eb)
        self.assertEqual(len(details), 1)
        self.assertEqual(details[0]['deskripsi'], 'Jasa konsultasi')
        self.assertEqual(details[0]['jumlah'], Decimal('2000'))
        self.assertEqual(details[0]['revenue_account'], akun_pend)

    def test_adapter_raises_without_profil(self):
        header = PendapatanHeader.objects.create(
            tanggal=date(2026, 1, 10), payment_type='credit', status='draft')
        from apps.pendapatan.services import pendapatan_to_piutang_payload
        with self.assertRaises(ValueError):
            pendapatan_to_piutang_payload(header)


class ConfirmCreditTest(TestCase):
    def _akun(self, kode, nama, kategori_id='aset'):
        return Akun.objects.create(kode_akun=kode, nama=nama, kategori_id=kategori_id)

    def _stt(self, akun_offset=None):
        if akun_offset is None:
            akun_offset = self._akun('2.1.9', 'Offset')
        return SubTransactionType.objects.create(
            nama='Pendapatan Jasa', module='pendapatan', direction='inflow',
            default_offset_account=akun_offset)

    def test_confirm_credit_builds_full_piutang_and_books_ar(self):
        from apps.jurnal.models import JurnalDetail
        from apps.piutang.models import PiutangHeader
        from apps.pendapatan.services import confirm_pendapatan

        akun_piutang = self._akun('1.1.4', 'Piutang Usaha')
        akun_pend = self._akun('4.1.1', 'Pendapatan Jasa', kategori_id='pendapatan')
        # A separate cash account — NOT the piutang account — is set as payment_account
        # so the test can prove the debit came from profil.coa_piutang_account, not pay_acct.
        akun_kas = self._akun('1.1.1', 'Kas')

        tipe = TipeEntitas.objects.create(nama='Umum')
        eb = EntitasBisnis.objects.create(nama='PT Beta', standar_akuntansi='psak', tipe_entitas=tipe)

        header = PendapatanHeader.objects.create(
            tanggal=date(2026, 3, 15), payment_type='credit', status='draft',
        )
        eb_group = PendapatanEntitasBisnis.objects.create(
            pendapatan_header=header, entitas_bisnis=eb,
            payment_account=akun_kas,  # cash account — should NOT be debited
        )
        KewajibabPelaksanaan.objects.create(
            pendapatan_eb=eb_group,
            deskripsi_item='Jasa konsultasi kredit',
            kategori='jasa',
            sub_transaction_type=self._stt(),
            nilai_kontrak=Decimal('2000'),
            revenue_account=akun_pend,
            recognition_type=KewajibabPelaksanaan.RecognitionType.POINT_IN_TIME,
        )
        PendapatanPiutangProfil.objects.create(
            pendapatan_header=header,
            debitur='PT Beta',
            coa_piutang_account=akun_piutang,
            jenis_bunga='flat',
            suku_bunga=Decimal('10'),
        )

        confirm_pendapatan(header, user=None)
        header.refresh_from_db()
        self.assertEqual(header.status, 'confirmed')

        # Full piutang created with credit terms from profil.
        piutang = PiutangHeader.objects.get(source_pendapatan=header)
        self.assertEqual(piutang.jumlah_pokok, Decimal('2000'))
        self.assertEqual(piutang.jenis_bunga, 'flat')
        self.assertEqual(piutang.coa_piutang_account, akun_piutang)

        # AR journal debits the piutang account (not the cash/payment account).
        debit_lines = JurnalDetail.objects.filter(akun=akun_piutang, debit=Decimal('2000'))
        self.assertTrue(debit_lines.exists(), 'Expected debit on piutang account, found none.')

        # Cash account must NOT be debited.
        cash_debit = JurnalDetail.objects.filter(akun=akun_kas, debit__gt=0)
        self.assertFalse(cash_debit.exists(), 'Cash account should not be debited for credit PIT.')

    def test_confirm_credit_raises_without_profil(self):
        from apps.pendapatan.services import confirm_pendapatan

        akun_pend = self._akun('4.1.2', 'Pendapatan Jasa 2', kategori_id='pendapatan')
        akun_kas = self._akun('1.1.2', 'Kas 2')
        tipe = TipeEntitas.objects.create(nama='Lainnya')
        eb = EntitasBisnis.objects.create(nama='PT Gamma', standar_akuntansi='psak', tipe_entitas=tipe)

        header = PendapatanHeader.objects.create(
            tanggal=date(2026, 3, 15), payment_type='credit', status='draft',
        )
        eb_group = PendapatanEntitasBisnis.objects.create(
            pendapatan_header=header, entitas_bisnis=eb, payment_account=akun_kas,
        )
        KewajibabPelaksanaan.objects.create(
            pendapatan_eb=eb_group,
            deskripsi_item='Jasa tanpa profil',
            kategori='jasa',
            sub_transaction_type=self._stt(akun_kas),
            nilai_kontrak=Decimal('1000'),
            revenue_account=akun_pend,
            recognition_type=KewajibabPelaksanaan.RecognitionType.POINT_IN_TIME,
        )
        # No PendapatanPiutangProfil created — should raise ValueError.
        with self.assertRaises(ValueError):
            confirm_pendapatan(header, user=None)


# ---------------------------------------------------------------------------
# Task 7: View-level tests — create/edit wires piutang profil
# ---------------------------------------------------------------------------

from django.contrib.auth import get_user_model
from django.urls import reverse


def _make_user():
    User = get_user_model()
    return User.objects.create_user(email='viewtest@naveda.id', password='testpass123')


def _tipe():
    return TipeEntitas.objects.create(nama='ViewTest')


def _stt_for_view(akun_offset):
    return SubTransactionType.objects.create(
        nama='Jasa View', module='pendapatan', direction='inflow',
        default_offset_account=akun_offset,
    )


class PendapatanCreateViewProfilTest(TestCase):
    """Test that pendapatan_create view validates and persists PendapatanPiutangProfil
    for credit transactions, and rejects credit POST without valid piutang fields."""

    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)
        # Create accounts used across tests
        self.akun_piutang = Akun.objects.create(kode_akun='1.1.4', nama='Piutang Usaha', kategori_id='aset')
        self.akun_pend = Akun.objects.create(kode_akun='4.1.1', nama='Pendapatan Jasa', kategori_id='pendapatan')
        self.akun_kas = Akun.objects.create(kode_akun='1.1.1', nama='Kas', kategori_id='aset')
        self.tipe = _tipe()
        self.eb = EntitasBisnis.objects.create(
            nama='PT View Test', standar_akuntansi='psak', tipe_entitas=self.tipe,
        )
        self.stt = _stt_for_view(self.akun_pend)
        from apps.accounts.models import UserEntitasBisnis
        UserEntitasBisnis.objects.create(user=self.user, entitas_bisnis=self.eb)

    def _base_post_data(self, payment_type='credit'):
        """Minimal valid POST data for pendapatan_create (one item)."""
        return {
            'tanggal': '2026-06-01',
            'payment_type': payment_type,
            'deskripsi': 'Test view create',
            'standar_akuntansi': 'PSAK_71_72',
            'item_count': '1',
            'eb_selection': f'lv1:{self.eb.pk}',
            'item_0-deskripsi_item': 'Item test',
            'item_0-kategori': 'jasa',
            'item_0-sub_transaction_type': str(self.stt.pk),
            'item_0-nilai_kontrak': '5000.00',
            'item_0-revenue_account': str(self.akun_pend.pk),
            'item_0-payment_account': str(self.akun_kas.pk),
            'item_0-recognition_type': 'point_in_time',
            'item_0-ot_tipe_aliran': '',
            'item_0-ot_progress_method': '',
        }

    def _piutang_fields(self):
        """Valid piutang-prefixed POST fields for PiutangHeaderForm(prefix='piutang')."""
        return {
            'piutang-tanggal': '2026-06-01',
            'piutang-debitur': 'PT View Test',
            'piutang-jenis_jangka_waktu': 'short_term',
            'piutang-coa_piutang_account': str(self.akun_piutang.pk),
            'piutang-jenis_bunga': 'tanpa_bunga',
            'piutang-suku_bunga': '0',
            'piutang-periode_angsuran': 'bulanan',
            'piutang-is_approval_required': '',
            'piutang-kategori_pengukuran': 'amortised_cost',
        }

    def test_credit_post_with_piutang_fields_saves_profil(self):
        """A valid credit POST with piutang-* fields should create PendapatanPiutangProfil."""
        post_data = {**self._base_post_data(payment_type='credit'), **self._piutang_fields()}
        response = self.client.post(reverse('pendapatan:create'), post_data, follow=False)

        # Should redirect to detail on success
        self.assertEqual(response.status_code, 302, msg=f"Expected redirect, got {response.status_code}")

        # Header was created
        self.assertEqual(PendapatanHeader.objects.count(), 1)
        header = PendapatanHeader.objects.first()
        self.assertEqual(header.payment_type, 'credit')

        # PendapatanPiutangProfil was persisted
        self.assertTrue(
            PendapatanPiutangProfil.objects.filter(pendapatan_header=header).exists(),
            msg='PendapatanPiutangProfil was not created for credit header.',
        )
        profil = PendapatanPiutangProfil.objects.get(pendapatan_header=header)
        self.assertEqual(profil.coa_piutang_account, self.akun_piutang)
        self.assertEqual(profil.debitur, 'PT View Test')

    def test_credit_post_without_piutang_account_rejected(self):
        """A credit POST that omits coa_piutang_account should re-render (HTTP 200) and
        leave no PendapatanHeader in the database (header is rolled back)."""
        post_data = self._base_post_data(payment_type='credit')
        # Deliberately omit piutang-coa_piutang_account — the form should fail validation
        post_data.update({
            'piutang-tanggal': '2026-06-01',
            'piutang-debitur': 'PT View Test',
            'piutang-jenis_jangka_waktu': 'short_term',
            # missing piutang-coa_piutang_account
            'piutang-jenis_bunga': 'tanpa_bunga',
            'piutang-periode_angsuran': 'bulanan',
        })

        response = self.client.post(reverse('pendapatan:create'), post_data, follow=False)

        # Should re-render the form (HTTP 200), not redirect
        self.assertEqual(response.status_code, 200, msg='Expected re-render when piutang form invalid.')

        # No header should remain in the database
        self.assertEqual(
            PendapatanHeader.objects.count(), 0,
            msg='Header should be rolled back when piutang form validation fails.',
        )

    def test_cash_post_does_not_create_profil(self):
        """A valid cash POST should NOT create a PendapatanPiutangProfil."""
        post_data = self._base_post_data(payment_type='cash')
        response = self.client.post(reverse('pendapatan:create'), post_data, follow=False)

        self.assertEqual(response.status_code, 302, msg=f"Expected redirect for cash, got {response.status_code}")
        self.assertEqual(PendapatanHeader.objects.count(), 1)
        self.assertEqual(PendapatanPiutangProfil.objects.count(), 0)

    def test_get_create_includes_piutang_form_in_context(self):
        """GET pendapatan_create should include piutang_form and piutang_profil_exists in context."""
        response = self.client.get(reverse('pendapatan:create'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('piutang_form', response.context, msg='piutang_form missing from GET context.')
        self.assertIn('piutang_profil_exists', response.context)
        self.assertFalse(response.context['piutang_profil_exists'])
        self.assertIn('eb_standar_map_json', response.context)
