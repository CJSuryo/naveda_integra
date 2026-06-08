from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.jurnal.models import JurnalDetail, JurnalHeader

from .models import (
    PiutangAuditLog, PiutangAttachment, PiutangDetail, PiutangHeader,
    PiutangPenerimaan, PiutangReklasifikasi, PiutangWriteOff,
)


# ── Audit Helper ──────────────────────────────────────────────────────────────

def _log(piutang: PiutangHeader, action: str, user=None, before=None, after=None, notes=''):
    PiutangAuditLog.objects.create(
        piutang_header=piutang,
        nomor_piutang=piutang.nomor_piutang,
        action=action,
        user=user,
        before_json=before or {},
        after_json=after or {},
        notes=notes,
    )


def _snapshot(piutang: PiutangHeader) -> dict:
    return {
        'status': piutang.status,
        'jumlah_pokok': str(piutang.jumlah_pokok),
        'jumlah_terbayar': str(piutang.jumlah_terbayar),
    }


def _next_piutang_journal_number(prefix: str) -> str:
    with transaction.atomic():
        last = (
            JurnalHeader.objects
            .select_for_update()
            .filter(nomor_transaksi__startswith=f'{prefix}-')
            .order_by('-nomor_transaksi')
            .values_list('nomor_transaksi', flat=True)
            .first()
        )
        seq = 1
        if last:
            try:
                seq = int(last.rsplit('-', 1)[1]) + 1
            except (ValueError, IndexError):
                seq = 1
        return f'{prefix}-{seq:04d}'


# ── Create ────────────────────────────────────────────────────────────────────

def create_manual_piutang(
    tanggal,
    entitas_bisnis,
    debitur: str,
    deskripsi: str,
    coa_piutang_account,
    jatuh_tempo,
    details: list,
    jenis_jangka_waktu: str = 'short_term',
    requires_approval: bool = False,
    jenis_bunga: str = 'tanpa_bunga',
    bunga_persen: Decimal = Decimal('0'),
    jumlah_angsuran=None,
    periode_angsuran: str = 'bulanan',
    user=None,
) -> PiutangHeader:
    if not details:
        raise ValueError('Minimal satu detail piutang diperlukan.')
    total = sum(Decimal(str(d['jumlah'])) for d in details)
    if total <= 0:
        raise ValueError('Total piutang harus lebih besar dari 0.')

    with transaction.atomic():
        piutang = PiutangHeader.objects.create(
            tanggal=tanggal,
            entitas_bisnis=entitas_bisnis,
            debitur=debitur,
            deskripsi=deskripsi,
            coa_piutang_account=coa_piutang_account,
            jatuh_tempo=jatuh_tempo,
            jumlah_pokok=total,
            status='draft',
            jenis_jangka_waktu=jenis_jangka_waktu,
            requires_approval=requires_approval,
            approval_status='pending' if requires_approval else '',
            jenis_bunga=jenis_bunga,
            bunga_persen=bunga_persen,
            jumlah_angsuran=jumlah_angsuran,
            periode_angsuran=periode_angsuran,
            created_by=user,
        )
        PiutangDetail.objects.bulk_create([
            PiutangDetail(
                piutang_header=piutang,
                deskripsi=d.get('deskripsi', ''),
                jumlah=Decimal(str(d['jumlah'])),
                revenue_account=d.get('revenue_account'),
                sub_transaction_type=d.get('sub_transaction_type'),
            )
            for d in details
        ])
        _log(piutang, 'CREATED', user=user, after=_snapshot(piutang))
    return piutang


# ── Stubs for callers that will be implemented in later phases ─────────────────

def create_piutang_from_sales(sales_header, user=None) -> PiutangHeader:
    raise NotImplementedError('Implemented in Phase 2 after SalesHeader.payment_type is added.')


def create_piutang_from_pendapatan(pendapatan_header, user=None) -> PiutangHeader:
    raise NotImplementedError('Implemented in Phase 3 after apps/pendapatan/ is ready.')


# ── Payment ───────────────────────────────────────────────────────────────────

def create_piutang_payment(piutang: PiutangHeader, data: dict, user=None) -> PiutangPenerimaan:
    jumlah = Decimal(str(data['jumlah_diterima']))
    with transaction.atomic():
        # Lock the piutang row for the duration of this transaction to prevent concurrent payment races
        piutang = PiutangHeader.objects.select_for_update().get(pk=piutang.pk)
        if jumlah > piutang.sisa_piutang:
            raise ValueError(
                f'Jumlah diterima ({jumlah}) melebihi sisa piutang ({piutang.sisa_piutang}).'
            )
        penerimaan = PiutangPenerimaan.objects.create(
            piutang_header=piutang,
            tanggal_terima=data['tanggal_terima'],
            jumlah_diterima=jumlah,
            angsuran_no=data.get('angsuran_no'),
            payment_account=data['payment_account'],
            metode_penerimaan=data.get('metode_penerimaan', 'transfer'),
            nomor_referensi=data.get('nomor_referensi', ''),
            catatan=data.get('catatan', ''),
            created_by=user,
        )
        jurnal = _create_payment_journal(piutang, penerimaan)
        penerimaan.jurnal_header = jurnal
        penerimaan.save(update_fields=['jurnal_header'])

        total_paid = piutang.penerimaan.aggregate(s=Sum('jumlah_diterima'))['s'] or Decimal('0')
        piutang.jumlah_terbayar = total_paid
        if total_paid >= piutang.jumlah_pokok:
            piutang.status = 'paid'
        elif total_paid > 0:
            piutang.status = 'partial'
        piutang.save(update_fields=['jumlah_terbayar', 'status'])

        _log(piutang, 'PAYMENT', user=user, after=_snapshot(piutang))
    return penerimaan


def _create_payment_journal(piutang: PiutangHeader, penerimaan: PiutangPenerimaan) -> JurnalHeader:
    nomor = _next_piutang_journal_number('TRX-PIU-P')
    header = JurnalHeader.objects.create(
        tanggal=penerimaan.tanggal_terima,
        nomor_transaksi=nomor,
        uraian_transaksi=f'Penerimaan Piutang {piutang.nomor_piutang} — {piutang.entitas_display}',
        entitas_bisnis=piutang.entitas_bisnis,
        is_penyesuaian=False,
    )
    JurnalDetail.objects.bulk_create([
        JurnalDetail(
            jurnal_header=header,
            akun=penerimaan.payment_account,
            debit=penerimaan.jumlah_diterima,
            kredit=Decimal('0'),
        ),
        JurnalDetail(
            jurnal_header=header,
            akun=piutang.coa_piutang_account,
            debit=Decimal('0'),
            kredit=penerimaan.jumlah_diterima,
        ),
    ])
    return header


def compute_angsuran_schedule(piutang: PiutangHeader) -> list[dict]:
    if not piutang.jumlah_angsuran or piutang.jumlah_angsuran <= 0:
        return []
    n = piutang.jumlah_angsuran
    pokok = piutang.jumlah_pokok
    rate_annual = piutang.bunga_persen / Decimal('100')

    period_months = {'bulanan': 1, 'triwulanan': 3, 'semesteran': 6, 'tahunan': 12}
    m = period_months.get(piutang.periode_angsuran, 1)
    rate_period = rate_annual * m / Decimal('12')

    result = []
    if piutang.jenis_bunga == 'tanpa_bunga':
        base_pokok = (pokok / n).quantize(Decimal('0.01'))
        remainder = pokok - base_pokok * (n - 1)
        for i in range(1, n + 1):
            p = remainder if i == n else base_pokok
            result.append({'no': i, 'pokok': p, 'bunga': Decimal('0'), 'angsuran': p})

    elif piutang.jenis_bunga == 'flat':
        base_pokok = (pokok / n).quantize(Decimal('0.01'))
        bunga_period = (pokok * rate_period).quantize(Decimal('0.01'))
        remainder = pokok - base_pokok * (n - 1)
        for i in range(1, n + 1):
            p = remainder if i == n else base_pokok
            result.append({'no': i, 'pokok': p, 'bunga': bunga_period, 'angsuran': p + bunga_period})

    elif piutang.jenis_bunga == 'anuitas':
        if rate_period == 0:
            return compute_angsuran_schedule(
                type('obj', (), {
                    'jumlah_angsuran': n, 'jumlah_pokok': pokok, 'jenis_bunga': 'tanpa_bunga',
                    'bunga_persen': Decimal('0'), 'periode_angsuran': piutang.periode_angsuran,
                })()
            )
        factor = rate_period * (1 + rate_period) ** n / ((1 + rate_period) ** n - 1)
        angsuran_tetap = (pokok * factor).quantize(Decimal('0.01'))
        saldo = pokok
        for i in range(1, n + 1):
            bunga = (saldo * rate_period).quantize(Decimal('0.01'))
            p = (angsuran_tetap - bunga).quantize(Decimal('0.01'))
            if i == n:
                p = saldo.quantize(Decimal('0.01'))
            result.append({'no': i, 'pokok': p, 'bunga': bunga, 'angsuran': p + bunga})
            saldo -= p

    return result


def compute_bagian_lancar(piutang: PiutangHeader) -> Decimal:
    if not piutang.jatuh_tempo:
        return Decimal('0')
    today = timezone.now().date()
    cutoff = today.replace(year=today.year + 1)
    if piutang.jatuh_tempo <= cutoff:
        return piutang.sisa_piutang
    return Decimal('0')
