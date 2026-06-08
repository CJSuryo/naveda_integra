from __future__ import annotations

from decimal import Decimal

from django.db import transaction
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
