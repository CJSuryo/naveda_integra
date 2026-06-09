from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.jurnal.models import JurnalDetail, JurnalHeader

from .models import PendapatanEntitasBisnis, PendapatanEventLog, PendapatanHeader, PendapatanItem


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log_event(header: PendapatanHeader, event_type: str, description: str = '', actor=None) -> None:
    PendapatanEventLog.objects.create(
        pendapatan_header=header,
        event_type=event_type,
        description=description,
        actor=actor,
    )


def _next_journal_number(prefix: str) -> str:
    """Atomic sequence generator for journal numbers."""
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


# ── Recurring Utilities ───────────────────────────────────────────────────────

def compute_next_date(current_date, frekuensi: str):
    from dateutil.relativedelta import relativedelta

    DELTA_MAP = {
        'harian': timedelta(days=1),
        'mingguan': timedelta(weeks=1),
        'bulanan': relativedelta(months=1),
        'triwulanan': relativedelta(months=3),
        'semesteran': relativedelta(months=6),
        'tahunan': relativedelta(years=1),
    }
    delta = DELTA_MAP.get(frekuensi)
    if delta is None:
        raise ValueError(f'Frekuensi tidak dikenal: {frekuensi}')
    return current_date + delta


def generate_from_recurring(template, user=None) -> PendapatanHeader:
    with transaction.atomic():
        header = PendapatanHeader.objects.create(
            tanggal=template.tanggal_berikutnya,
            deskripsi=f'{template.nama} — {template.tanggal_berikutnya}',
            payment_type=template.payment_type,
            source_type='recurring',
            source_recurring=template,
            status='draft',
            created_by=user,
        )

        eb_group = PendapatanEntitasBisnis.objects.create(
            pendapatan_header=header,
            entitas_bisnis=template.entitas_bisnis,
            entitas_bisnis_lv2=template.entitas_bisnis_lv2,
            entitas_bisnis_lv3=template.entitas_bisnis_lv3,
        )

        PendapatanItem.objects.create(
            pendapatan_eb=eb_group,
            deskripsi_item=template.deskripsi_item,
            kategori=template.kategori,
            sub_transaction_type=template.sub_transaction_type,
            jumlah_bruto=template.jumlah,
            revenue_account=template.revenue_account,
            payment_account=template.payment_account,
            is_deferred=False,
        )

        new_next = compute_next_date(template.tanggal_berikutnya, template.frekuensi)
        template.tanggal_berikutnya = new_next
        if template.tanggal_selesai and new_next > template.tanggal_selesai:
            template.is_active = False
        template.save(update_fields=['tanggal_berikutnya', 'is_active', 'updated_at'])

        _log_event(header, 'RECURRING_GENERATED', description=f'Generated from template {template.pk}', actor=user)

        if template.auto_confirm:
            confirm_pendapatan(header, user=user)

    return header


# ── Create ────────────────────────────────────────────────────────────────────

def create_pendapatan_header(
    tanggal,
    deskripsi: str,
    payment_type: str,
    entitas_bisnis,
    payment_account,
    items: list,
    entitas_bisnis_lv2=None,
    entitas_bisnis_lv3=None,
    source_type: str = 'manual',
    user=None,
) -> PendapatanHeader:
    if not items:
        raise ValueError('Minimal satu item pendapatan diperlukan.')

    with transaction.atomic():
        header = PendapatanHeader.objects.create(
            tanggal=tanggal,
            deskripsi=deskripsi,
            payment_type=payment_type,
            source_type=source_type,
            status='draft',
            created_by=user,
        )

        eb_group = PendapatanEntitasBisnis.objects.create(
            pendapatan_header=header,
            entitas_bisnis=entitas_bisnis,
            entitas_bisnis_lv2=entitas_bisnis_lv2,
            entitas_bisnis_lv3=entitas_bisnis_lv3,
            payment_account=payment_account,
        )

        PendapatanItem.objects.bulk_create([
            PendapatanItem(
                pendapatan_eb=eb_group,
                deskripsi_item=item['deskripsi_item'],
                kategori=item['kategori'],
                sub_transaction_type=item['sub_transaction_type'],
                jumlah_bruto=item['jumlah_bruto'],
                revenue_account=item['revenue_account'],
                payment_account=item.get('payment_account'),
                tax=item.get('tax'),
                tax_type=item.get('tax_type', ''),
                tax_account=item.get('tax_account'),
                tax_payment=item.get('tax_payment', ''),
                tax_payment_account=item.get('tax_payment_account'),
                is_deferred=item.get('is_deferred', False),
                deferred_account=item.get('deferred_account'),
                recognition_account=item.get('recognition_account'),
                deferred_tanggal_mulai=item.get('deferred_tanggal_mulai'),
                deferred_tanggal_selesai=item.get('deferred_tanggal_selesai'),
                deferred_metode=item.get('deferred_metode', 'straight_line'),
            )
            for item in items
        ])

        _log_event(header, 'CREATED', actor=user)

    return header


# ── Confirm ───────────────────────────────────────────────────────────────────

def confirm_pendapatan(header: PendapatanHeader, user=None) -> None:
    if header.status != 'draft':
        raise ValueError(
            f'Pendapatan {header.transaction_id} tidak dapat dikonfirmasi '
            f'karena status-nya adalah "{header.status}" (bukan "draft").'
        )

    with transaction.atomic():
        _create_pendapatan_journals(header, user)

        if header.payment_type == 'credit':
            from apps.piutang.services import create_piutang_from_pendapatan
            piutang = create_piutang_from_pendapatan(header, user)
            _log_event(header, 'PIUTANG_CREATED', description=piutang.nomor_piutang, actor=user)

        # Create deferred schedules for deferred items
        from .deferred_services import create_deferred_schedule
        deferred_count = 0
        for eb_group in header.entitas_groups.prefetch_related('items').all():
            for item in eb_group.items.filter(is_deferred=True):
                create_deferred_schedule(item)
                deferred_count += 1
        if deferred_count:
            _log_event(header, 'DEFERRED_SCHEDULED', description=f'{deferred_count} jadwal dibuat', actor=user)

        header.status = 'confirmed'
        header.save(update_fields=['status'])
        _log_event(header, 'CONFIRMED', actor=user)


# ── Void ──────────────────────────────────────────────────────────────────────

def void_pendapatan(header: PendapatanHeader, user=None) -> None:
    if header.status != 'confirmed':
        raise ValueError(
            f'Pendapatan {header.transaction_id} tidak dapat dibatalkan '
            f'karena status-nya adalah "{header.status}" (bukan "confirmed").'
        )
    if header.is_locked:
        raise ValueError(
            f'Pendapatan {header.transaction_id} terkunci dan tidak dapat dibatalkan.'
        )

    with transaction.atomic():
        # Reverse all journals linked to this pendapatan header
        linked_journals = JurnalHeader.objects.filter(
            nomor_transaksi__startswith='TRX-PND-J',
            uraian_transaksi__icontains=header.transaction_id,
        )
        for jh in linked_journals:
            reversal_num = _next_journal_number('TRX-PND-R')
            rev_header = JurnalHeader.objects.create(
                tanggal=timezone.now().date(),
                nomor_transaksi=reversal_num,
                uraian_transaksi=f'Reversal {header.transaction_id} — {jh.nomor_transaksi}',
                entitas_bisnis=jh.entitas_bisnis,
                is_penyesuaian=True,
            )
            JurnalDetail.objects.bulk_create([
                JurnalDetail(
                    jurnal_header=rev_header,
                    akun=d.akun,
                    debit=d.kredit,
                    kredit=d.debit,
                )
                for d in jh.details.all()
            ])

        # Cancel linked piutang
        from apps.piutang.models import PiutangHeader
        linked_piutang = PiutangHeader.objects.filter(
            source_pendapatan=header,
            status__in=('open', 'draft'),
        )
        linked_piutang.update(status='cancelled')

        header.status = 'voided'
        header.save(update_fields=['status'])
        _log_event(header, 'VOIDED', actor=user)


# ── Journal Creation ──────────────────────────────────────────────────────────

def _create_pendapatan_journals(header: PendapatanHeader, user=None) -> None:
    for eb_group in header.entitas_groups.prefetch_related('items__revenue_account', 'items__payment_account').all():
        nomor = _next_journal_number('TRX-PND-J')
        jh = JurnalHeader.objects.create(
            tanggal=header.tanggal,
            nomor_transaksi=nomor,
            uraian_transaksi=f'Pendapatan {header.transaction_id} — {eb_group.entitas_bisnis.nama}',
            entitas_bisnis=eb_group.entitas_bisnis,
            is_penyesuaian=False,
        )

        entries = []
        for item in eb_group.items.all():
            pay_acct = item.payment_account or eb_group.payment_account
            cr_acct = (
                item.deferred_account
                if item.is_deferred and item.deferred_account
                else item.revenue_account
            )
            entries.append(JurnalDetail(
                jurnal_header=jh,
                akun=pay_acct,
                debit=item.jumlah_bruto,
                kredit=Decimal('0'),
            ))
            entries.append(JurnalDetail(
                jurnal_header=jh,
                akun=cr_acct,
                debit=Decimal('0'),
                kredit=item.jumlah_bruto,
            ))

            # Tax lines
            if item.tax and item.tax > 0 and item.tax_account:
                entries.append(JurnalDetail(
                    jurnal_header=jh,
                    akun=item.tax_account,
                    debit=Decimal('0'),
                    kredit=item.tax,
                ))

        JurnalDetail.objects.bulk_create(entries)
        _log_event(header, 'JOURNAL_CREATED', description=jh.nomor_transaksi, actor=user)


# ── Dashboard KPIs ────────────────────────────────────────────────────────────

def get_pendapatan_dashboard_kpi() -> dict:
    today = timezone.now().date()
    month_start = today.replace(day=1)

    # Start of last month
    if month_start.month == 1:
        last_month_start = month_start.replace(year=month_start.year - 1, month=12)
    else:
        last_month_start = month_start.replace(month=month_start.month - 1)
    last_month_end = month_start

    confirmed_qs = PendapatanHeader.objects.filter(status='confirmed')

    # This month
    this_month_qs = confirmed_qs.filter(tanggal__gte=month_start)
    total_bulan_ini = (
        PendapatanItem.objects
        .filter(pendapatan_eb__pendapatan_header__in=this_month_qs)
        .aggregate(s=Sum('jumlah_bruto'))['s'] or Decimal('0')
    )
    cash_bulan_ini = (
        PendapatanItem.objects
        .filter(
            pendapatan_eb__pendapatan_header__in=this_month_qs,
            pendapatan_eb__pendapatan_header__payment_type='cash',
        )
        .aggregate(s=Sum('jumlah_bruto'))['s'] or Decimal('0')
    )
    credit_bulan_ini = (
        PendapatanItem.objects
        .filter(
            pendapatan_eb__pendapatan_header__in=this_month_qs,
            pendapatan_eb__pendapatan_header__payment_type='credit',
        )
        .aggregate(s=Sum('jumlah_bruto'))['s'] or Decimal('0')
    )

    # Last month
    last_month_qs = confirmed_qs.filter(tanggal__gte=last_month_start, tanggal__lt=last_month_end)
    total_bulan_lalu = (
        PendapatanItem.objects
        .filter(pendapatan_eb__pendapatan_header__in=last_month_qs)
        .aggregate(s=Sum('jumlah_bruto'))['s'] or Decimal('0')
    )

    return {
        'total_bulan_ini': total_bulan_ini,
        'total_bulan_lalu': total_bulan_lalu,
        'cash_bulan_ini': cash_bulan_ini,
        'credit_bulan_ini': credit_bulan_ini,
    }
