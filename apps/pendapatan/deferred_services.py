from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction

from apps.jurnal.models import JurnalDetail, JurnalHeader

from .models import DeferredRevenueEntry, DeferredRevenueSchedule, PendapatanItem


def _iter_months(start: date, end: date):
    current = start.replace(day=1)
    end_key = end.replace(day=1)
    while current <= end_key:
        yield current
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)


def create_deferred_schedule(item: PendapatanItem) -> DeferredRevenueSchedule:
    if not item.is_deferred:
        raise ValueError('Item bukan deferred revenue.')
    if not item.deferred_tanggal_mulai or not item.deferred_tanggal_selesai:
        raise ValueError('Tanggal mulai dan selesai deferred harus diisi.')
    if not item.deferred_account or not item.recognition_account:
        raise ValueError('Akun deferred dan akun pengakuan harus diisi.')

    periods = list(_iter_months(item.deferred_tanggal_mulai, item.deferred_tanggal_selesai))
    if not periods:
        raise ValueError('Tidak ada periode yang valid antara tanggal mulai dan selesai.')

    n = len(periods)
    jumlah_total = item.jumlah_bruto
    metode = item.deferred_metode or 'straight_line'

    with transaction.atomic():
        schedule = DeferredRevenueSchedule.objects.create(
            pendapatan_item=item,
            jumlah_total=jumlah_total,
            tanggal_mulai=item.deferred_tanggal_mulai,
            tanggal_selesai=item.deferred_tanggal_selesai,
            metode=metode,
            recognition_account=item.recognition_account,
            deferred_account=item.deferred_account,
        )

        if metode == 'straight_line':
            base = (jumlah_total / n).quantize(Decimal('0.01'))
            remainder = jumlah_total - base * (n - 1)
            entries = [
                DeferredRevenueEntry(
                    schedule=schedule,
                    periode=p,
                    jumlah=remainder if i == n - 1 else base,
                    status='pending',
                )
                for i, p in enumerate(periods)
            ]
        else:
            entries = [
                DeferredRevenueEntry(schedule=schedule, periode=p, jumlah=Decimal('0'), status='pending')
                for p in periods
            ]

        DeferredRevenueEntry.objects.bulk_create(entries)
    return schedule


def recognize_deferred_entry(entry: DeferredRevenueEntry, user=None) -> JurnalHeader:
    if entry.status != 'pending':
        raise ValueError(f'Entry status harus pending, bukan {entry.status}.')

    with transaction.atomic():
        from apps.pendapatan.services import _next_journal_number
        nomor = _next_journal_number('TRX-PND-DR')
        header = JurnalHeader.objects.create(
            tanggal=entry.periode,
            nomor_transaksi=nomor,
            uraian_transaksi=(
                f'Pengakuan Deferred Revenue — '
                f'{entry.schedule.pendapatan_item.pendapatan_eb.pendapatan_header.transaction_id} '
                f'Periode {entry.periode.strftime("%Y-%m")}'
            ),
            is_penyesuaian=False,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(
                jurnal_header=header,
                akun=entry.schedule.deferred_account,
                debit=entry.jumlah,
                kredit=Decimal('0'),
            ),
            JurnalDetail(
                jurnal_header=header,
                akun=entry.schedule.recognition_account,
                debit=Decimal('0'),
                kredit=entry.jumlah,
            ),
        ])
        entry.status = 'recognized'
        entry.jurnal_header = header
        entry.save(update_fields=['status', 'jurnal_header'])
    return header


def reverse_deferred_entry(entry: DeferredRevenueEntry, user=None):
    if entry.status == 'pending':
        entry.status = 'reversed'
        entry.save(update_fields=['status'])
