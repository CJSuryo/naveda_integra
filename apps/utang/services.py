import calendar
from datetime import date
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from apps.jurnal.models import JurnalDetail, JurnalHeader
from apps.jurnal.utils import log_jurnal_terhapus

from .models import (
    UtangAuditLog, UtangAttachment, UtangDetail, UtangHeader,
    UtangPembayaran, UtangTerhapus,
)


# ── Audit Helper ──────────────────────────────────────────────────────────────

def _log_audit(utang: UtangHeader, action: str, user=None, before=None, after=None, notes=''):
    UtangAuditLog.objects.create(
        utang_header=utang,
        nomor_utang=utang.nomor_utang,
        action=action,
        user=user,
        before_json=before or {},
        after_json=after or {},
        notes=notes,
    )


def _utang_snapshot(utang: UtangHeader) -> dict:
    return {
        'status': utang.status,
        'approval_status': utang.approval_status,
        'total_amount': str(utang.total_amount),
        'jenis_utang': utang.jenis_utang,
        'kreditor': utang.kreditor,
    }


# ── Formation Journal ─────────────────────────────────────────────────────────

def _create_formation_journal(utang: UtangHeader) -> JurnalHeader:
    """Dr coa_source_account / Cr each detail's coa_utang_account."""
    if not utang.coa_source_account_id:
        raise ValueError('Akun asal (coa_source_account) diperlukan untuk jurnal pembentukan.')

    nomor = _next_utang_formation_journal_number()
    header = JurnalHeader.objects.create(
        tanggal=utang.tanggal,
        nomor_transaksi=nomor,
        uraian_transaksi=f'Pembentukan Utang {utang.nomor_utang} — {utang.kreditor or utang.entitas_display}',
        entitas_bisnis=utang.entitas_bisnis,
        is_penyesuaian=False,
    )
    details_list = list(utang.details.select_related('coa_utang_account').all())
    entries = [
        JurnalDetail(
            jurnal_header=header,
            akun=utang.coa_source_account,
            debit=utang.total_amount,
            kredit=Decimal('0'),
        )
    ]
    for d in details_list:
        entries.append(JurnalDetail(
            jurnal_header=header,
            akun=d.coa_utang_account,
            debit=Decimal('0'),
            kredit=d.amount,
        ))
    JurnalDetail.objects.bulk_create(entries)
    return header


def _next_utang_formation_journal_number() -> str:
    with transaction.atomic():
        last = (
            JurnalHeader.objects
            .select_for_update()
            .filter(nomor_transaksi__startswith='TRX-UTG-F-')
            .order_by('-nomor_transaksi')
            .values_list('nomor_transaksi', flat=True)
            .first()
        )
        if last:
            try:
                seq = int(last.rsplit('-', 1)[1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1
        return f'TRX-UTG-F-{seq:04d}'


# ── Create Manual Utang ───────────────────────────────────────────────────────

def create_manual_utang(
    tanggal,
    entitas_bisnis,
    deskripsi: str,
    jenis_utang: str,
    kreditor: str,
    nomor_referensi: str,
    kategori_jangka_waktu: str,
    coa_source_account,
    requires_approval: bool,
    tanggal_jatuh_tempo,
    details: list,  # [{'coa_utang_account': Akun, 'description': str, 'amount': Decimal}]
    user=None,
) -> UtangHeader:
    if not details:
        raise ValueError('Minimal satu detail utang diperlukan.')
    total = sum(Decimal(str(d['amount'])) for d in details)
    if total <= 0:
        raise ValueError('Total utang harus lebih besar dari 0.')

    with transaction.atomic():
        utang = UtangHeader.objects.create(
            tanggal=tanggal,
            entitas_bisnis=entitas_bisnis,
            deskripsi=deskripsi,
            jenis_utang=jenis_utang,
            kreditor=kreditor,
            nomor_referensi=nomor_referensi,
            kategori_jangka_waktu=kategori_jangka_waktu,
            coa_source_account=coa_source_account,
            requires_approval=requires_approval,
            tanggal_jatuh_tempo=tanggal_jatuh_tempo,
            total_amount=total,
            status='draft' if requires_approval else 'open',
            approval_status='pending' if requires_approval else '',
        )
        UtangDetail.objects.bulk_create([
            UtangDetail(
                utang_header=utang,
                coa_utang_account=d['coa_utang_account'],
                description=d.get('description', ''),
                amount=Decimal(str(d['amount'])),
            )
            for d in details
        ])
        if not requires_approval and coa_source_account:
            journal = _create_formation_journal(utang)
            utang.jurnal_pembentukan = journal
            utang.save(update_fields=['jurnal_pembentukan'])

        _log_audit(utang, 'CREATE', user=user, after=_utang_snapshot(utang))
    return utang


# ── Approval Flow ─────────────────────────────────────────────────────────────

def submit_utang_for_approval(utang: UtangHeader, user=None) -> None:
    if utang.status != 'draft':
        raise ValueError('Hanya utang berstatus Draft yang dapat diajukan untuk persetujuan.')
    before = _utang_snapshot(utang)
    utang.status = 'waiting_approval'
    utang.save(update_fields=['status'])
    _log_audit(utang, 'SUBMIT_APPROVAL', user=user, before=before, after=_utang_snapshot(utang))


def approve_utang(utang: UtangHeader, user=None) -> None:
    if utang.status not in ('draft', 'waiting_approval'):
        raise ValueError('Utang tidak dalam status yang dapat disetujui.')
    before = _utang_snapshot(utang)
    with transaction.atomic():
        utang.approval_status = 'approved'
        utang.approved_by = user
        utang.approved_at = timezone.now()
        if utang.coa_source_account_id:
            journal = _create_formation_journal(utang)
            utang.jurnal_pembentukan = journal
        utang.status = 'open'
        utang.save(update_fields=['approval_status', 'approved_by', 'approved_at', 'jurnal_pembentukan', 'status'])
        _log_audit(utang, 'APPROVE', user=user, before=before, after=_utang_snapshot(utang))


def reject_utang(utang: UtangHeader, user=None, notes: str = '') -> None:
    if utang.status not in ('draft', 'waiting_approval'):
        raise ValueError('Utang tidak dalam status yang dapat ditolak.')
    before = _utang_snapshot(utang)
    utang.approval_status = 'rejected'
    utang.status = 'cancelled'
    utang.save(update_fields=['approval_status', 'status'])
    _log_audit(utang, 'REJECT', user=user, before=before, after=_utang_snapshot(utang), notes=notes)


# ── Purchase Utang (unchanged) ────────────────────────────────────────────────

def create_utang_for_purchase(purchase_header, tanggal_jatuh_tempo=None):
    from datetime import timedelta
    utang_headers = []
    with transaction.atomic():
        for eb_group in (
            purchase_header.entitas_groups
            .select_related('entitas_bisnis')
            .prefetch_related(
                'items__offset_coa_account', 'items__coa_account',
                'items__item', 'items__sub_transaction_type',
            ).all()
        ):
            utang_items = [
                item for item in eb_group.items.all()
                if item.offset_coa_account
                and item.offset_coa_account.kategori_id == 'kewajiban'
            ]
            if not utang_items:
                continue
            groups: dict[int, list] = {}
            for item in utang_items:
                groups.setdefault(item.offset_coa_account_id, []).append(item)
            for coa_id, items in groups.items():
                total_amount = sum(item.total_value for item in items)
                stt = items[0].sub_transaction_type
                jatuh_tempo = None
                if stt and stt.payment_term_days:
                    jatuh_tempo = purchase_header.tanggal + timedelta(days=stt.payment_term_days)
                elif tanggal_jatuh_tempo:
                    jatuh_tempo = tanggal_jatuh_tempo
                header = UtangHeader.objects.create(
                    purchase_header=purchase_header,
                    tanggal=purchase_header.tanggal,
                    tanggal_jatuh_tempo=jatuh_tempo,
                    entitas_bisnis=eb_group.entitas_bisnis,
                    jenis_utang='usaha',
                    deskripsi=f'Utang dari {purchase_header.transaction_id}',
                    total_amount=total_amount,
                    status='open',
                )
                UtangDetail.objects.bulk_create([
                    UtangDetail(
                        utang_header=header,
                        purchase_item=item,
                        coa_utang_account_id=coa_id,
                        description=str(item.item),
                        amount=item.total_value,
                    )
                    for item in items
                ])
                utang_headers.append(header)
    return utang_headers


# ── Payment ───────────────────────────────────────────────────────────────────

def create_utang_payment(
    utang_header: UtangHeader, utang_detail, tanggal, coa_account, jumlah, keterangan, user=None,
):
    if jumlah <= 0:
        raise ValueError('Jumlah pembayaran harus lebih besar dari 0.')
    with transaction.atomic():
        locked = UtangHeader.objects.select_for_update().get(pk=utang_header.pk)
        outstanding = locked.outstanding_amount
        if jumlah > outstanding:
            raise ValueError('Jumlah pembayaran tidak boleh melebihi sisa utang.')
        payment = UtangPembayaran.objects.create(
            utang_header=locked, utang_detail=utang_detail,
            tanggal=tanggal, coa_account=coa_account,
            jumlah=jumlah, keterangan=keterangan,
        )
        journal = _create_utang_payment_journal(payment)
        payment.jurnal_header = journal
        payment.save(update_fields=['jurnal_header'])
        _update_utang_status(locked)
        _log_audit(locked, 'PAYMENT', user=user, after={'jumlah': str(jumlah), 'tanggal': str(tanggal)})
        return payment


def reverse_utang_header(utang_header: UtangHeader, user=None):
    before = _utang_snapshot(utang_header)
    with transaction.atomic():
        UtangTerhapus.objects.create(
            nomor_utang=utang_header.nomor_utang,
            uraian=utang_header.deskripsi,
            entitas_bisnis_nama=(str(utang_header.entitas_bisnis) if utang_header.entitas_bisnis else ''),
            tanggal=utang_header.tanggal,
            deleted_by=user,
            snapshot={
                'total_amount': str(utang_header.total_amount),
                'status': utang_header.status,
                'jenis_utang': utang_header.jenis_utang,
                'kreditor': utang_header.kreditor,
                'tanggal_jatuh_tempo': (
                    str(utang_header.tanggal_jatuh_tempo) if utang_header.tanggal_jatuh_tempo else None
                ),
                'details': [
                    {'coa': str(d.coa_utang_account), 'amount': str(d.amount), 'description': d.description}
                    for d in utang_header.details.select_related('coa_utang_account').all()
                ],
            },
        )
        if utang_header.jurnal_pembentukan_id:
            log_jurnal_terhapus(utang_header.jurnal_pembentukan, 'utang', None)
            utang_header.jurnal_pembentukan.delete()
        for payment in utang_header.pembayaran.select_related('jurnal_header').all():
            if payment.jurnal_header_id:
                log_jurnal_terhapus(payment.jurnal_header, 'utang', None)
                payment.jurnal_header.delete()
        _log_audit(utang_header, 'REVERSE', user=user, before=before)
        utang_header.delete()


def reverse_utang_for_purchase(purchase_header):
    for utang in purchase_header.utang_headers.select_related().all():
        reverse_utang_header(utang)


def reverse_utang_payment(payment: UtangPembayaran, user=None) -> None:
    utang_header = payment.utang_header
    with transaction.atomic():
        if payment.jurnal_header_id:
            log_jurnal_terhapus(payment.jurnal_header, 'utang', None)
            payment.jurnal_header.delete()
        payment.delete()
        _update_utang_status(utang_header)
        _log_audit(utang_header, 'REVERSE_PAYMENT', user=user)


# ── Attachments ───────────────────────────────────────────────────────────────

def upload_utang_attachment(utang: UtangHeader, file, jenis_dokumen: str, user=None) -> UtangAttachment:
    attachment = UtangAttachment.objects.create(
        utang_header=utang,
        file=file,
        file_name=file.name,
        jenis_dokumen=jenis_dokumen,
        uploaded_by=user,
    )
    _log_audit(utang, 'EDIT', user=user, notes=f'Upload dokumen: {file.name}')
    return attachment


def delete_utang_attachment(attachment: UtangAttachment, user=None) -> None:
    utang = attachment.utang_header
    name = attachment.file_name
    attachment.file.delete(save=False)
    attachment.delete()
    _log_audit(utang, 'EDIT', user=user, notes=f'Hapus dokumen: {name}')


# ── Internal helpers ──────────────────────────────────────────────────────────

def _create_utang_payment_journal(payment: UtangPembayaran) -> JurnalHeader:
    utang_header = payment.utang_header
    if payment.utang_detail:
        utang_account = payment.utang_detail.coa_utang_account
    else:
        first_detail = utang_header.details.first()
        utang_account = first_detail.coa_utang_account if first_detail else None
    if not utang_account:
        raise ValueError('Tidak ada akun utang untuk pembayaran ini.')
    nomor = _next_utang_payment_journal_number()
    header = JurnalHeader.objects.create(
        tanggal=payment.tanggal,
        nomor_transaksi=nomor,
        uraian_transaksi=f'Pembayaran Utang {utang_header.nomor_utang}',
        entitas_bisnis=utang_header.entitas_bisnis,
        is_penyesuaian=False,
    )
    JurnalDetail.objects.bulk_create([
        JurnalDetail(jurnal_header=header, akun=utang_account, debit=payment.jumlah, kredit=Decimal('0')),
        JurnalDetail(jurnal_header=header, akun=payment.coa_account, debit=Decimal('0'), kredit=payment.jumlah),
    ])
    return header


def _next_utang_payment_journal_number() -> str:
    with transaction.atomic():
        last = (
            JurnalHeader.objects
            .select_for_update()
            .filter(nomor_transaksi__startswith='TRX-UTG-')
            .exclude(nomor_transaksi__startswith='TRX-UTG-F-')
            .order_by('-nomor_transaksi')
            .values_list('nomor_transaksi', flat=True)
            .first()
        )
        if last:
            try:
                seq = int(last.rsplit('-', 1)[1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1
        return f'TRX-UTG-{seq:04d}'


def _update_utang_status(utang_header: UtangHeader) -> None:
    paid = utang_header.paid_amount
    if paid >= utang_header.total_amount:
        utang_header.status = 'paid'
    elif paid > 0:
        utang_header.status = 'partial'
    else:
        utang_header.status = 'open'
    utang_header.save(update_fields=['status'])


# ── Bagian Lancar / JT Utang ─────────────────────────────────────────────────

_PERIODE_MONTHS_MAP = {'bulanan': 1, 'triwulanan': 3, 'semesteran': 6, 'tahunan': 12}


def _add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return d.replace(year=year, month=month, day=day)


def _compute_installment_principals(utang: UtangHeader) -> list[tuple[date, Decimal]]:
    """
    Returns [(tanggal, principal)] for all installments.
    Dates start from utang.tanggal + 1 period; n is auto-computed from date range.
    """
    if not utang.tanggal_jatuh_tempo:
        return []
    periode_months = _PERIODE_MONTHS_MAP.get(utang.periode_angsuran, 1)
    total_months = (
        (utang.tanggal_jatuh_tempo.year - utang.tanggal.year) * 12
        + (utang.tanggal_jatuh_tempo.month - utang.tanggal.month)
    )
    if total_months <= 0:
        return []
    n = max(1, round(total_months / periode_months))
    total = float(utang.total_amount)
    jenis = utang.jenis_bunga
    r = float(utang.suku_bunga) / 100 / 12 * periode_months if jenis != 'tanpa_bunga' else 0.0
    schedule = []
    if jenis == 'anuitas' and r > 0:
        pmt = total * r / (1 - (1 + r) ** (-n))
        sisa = total
        for i in range(n):
            bunga_i = sisa * r
            pk_i = pmt - bunga_i
            if i == n - 1:
                pk_i = sisa
            sisa -= pk_i
            schedule.append((_add_months(utang.tanggal, (i + 1) * periode_months), Decimal(str(round(pk_i, 4)))))
    else:
        pk_i = Decimal(str(round(total / n, 4)))
        for i in range(n):
            schedule.append((_add_months(utang.tanggal, (i + 1) * periode_months), pk_i))
    return schedule


def compute_bagian_lancar(utang: UtangHeader) -> dict:
    """
    Returns {'bagian_lancar': Decimal, 'bagian_panjang': Decimal, 'has_schedule': bool, 'n_angsuran': int}.
    Bagian lancar = outstanding amount due within next 12 months from today.
    Always computes installment schedule from tanggal → tanggal_jatuh_tempo when both are set.
    """
    outstanding = utang.outstanding_amount
    if outstanding <= 0:
        return {'bagian_lancar': Decimal('0'), 'bagian_panjang': Decimal('0'), 'has_schedule': False, 'n_angsuran': 0}

    today = date.today()
    cutoff = _add_months(today, 12)

    if utang.tanggal_jatuh_tempo:
        schedule = _compute_installment_principals(utang)
        if schedule:
            future = [(tgl, pk) for tgl, pk in schedule if tgl > today]
            if not future:
                return {'bagian_lancar': outstanding, 'bagian_panjang': Decimal('0'), 'has_schedule': True, 'n_angsuran': len(schedule)}
            future_pk = sum(pk for _, pk in future)
            lancar_pk = sum(pk for tgl, pk in future if tgl <= cutoff)
            if future_pk > 0:
                ratio = float(lancar_pk) / float(future_pk)
                bl = (outstanding * Decimal(str(round(ratio, 8)))).quantize(Decimal('0.01'))
                bp = (outstanding - bl).quantize(Decimal('0.01'))
                return {'bagian_lancar': bl, 'bagian_panjang': bp, 'has_schedule': True, 'n_angsuran': len(schedule)}

        # Fallback: bullet repayment on single due date
        if utang.tanggal_jatuh_tempo <= cutoff:
            return {'bagian_lancar': outstanding, 'bagian_panjang': Decimal('0'), 'has_schedule': False, 'n_angsuran': 0}
        return {'bagian_lancar': Decimal('0'), 'bagian_panjang': outstanding, 'has_schedule': False, 'n_angsuran': 0}

    return {'bagian_lancar': outstanding, 'bagian_panjang': Decimal('0'), 'has_schedule': False, 'n_angsuran': 0}


def get_bagian_lancar_list() -> list[dict]:
    """All active long-term utang with their bagian_lancar breakdown, sorted by bagian_lancar desc."""
    qs = list(
        UtangHeader.objects
        .filter(status__in=['open', 'partial', 'overdue'], kategori_jangka_waktu='long_term')
        .select_related('entitas_bisnis')
        .prefetch_related('pembayaran')
    )
    result = []
    for u in qs:
        bl = compute_bagian_lancar(u)
        result.append({'utang': u, **bl})
    result.sort(key=lambda x: x['bagian_lancar'], reverse=True)
    return result


# ── Reklasifikasi Journal ─────────────────────────────────────────────────────

def _next_utang_reklasifikasi_journal_number() -> str:
    with transaction.atomic():
        last = (
            JurnalHeader.objects
            .select_for_update()
            .filter(nomor_transaksi__startswith='TRX-UTG-RKL-')
            .order_by('-nomor_transaksi')
            .values_list('nomor_transaksi', flat=True)
            .first()
        )
        try:
            seq = int(last.rsplit('-', 1)[1]) + 1 if last else 1
        except (ValueError, IndexError):
            seq = 1
        return f'TRX-UTG-RKL-{seq:04d}'


def create_reklasifikasi_journal(
    utang: UtangHeader, coa_bagian_lancar, tanggal=None, user=None,
) -> None:
    """
    Dr utang.detail[largest].coa_utang_account  bagian_lancar
    Cr coa_bagian_lancar                         bagian_lancar
    Marks as is_penyesuaian=True.
    """
    if utang.jurnal_reklasifikasi_id:
        raise ValueError('Jurnal reklasifikasi sudah ada. Batalkan dulu sebelum membuat baru.')
    bl = compute_bagian_lancar(utang)
    jumlah = bl['bagian_lancar']
    if jumlah <= 0:
        raise ValueError('Bagian lancar adalah 0, tidak perlu jurnal reklasifikasi.')

    detail = utang.details.order_by('-amount').select_related('coa_utang_account').first()
    if not detail:
        raise ValueError('Tidak ada detail utang.')
    tanggal_jurnal = tanggal or date.today()

    with transaction.atomic():
        nomor = _next_utang_reklasifikasi_journal_number()
        header = JurnalHeader.objects.create(
            tanggal=tanggal_jurnal,
            nomor_transaksi=nomor,
            uraian_transaksi=f'Reklasifikasi Bagian Lancar {utang.nomor_utang}',
            entitas_bisnis=utang.entitas_bisnis,
            is_penyesuaian=True,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(jurnal_header=header, akun=detail.coa_utang_account, debit=jumlah, kredit=Decimal('0')),
            JurnalDetail(jurnal_header=header, akun=coa_bagian_lancar, debit=Decimal('0'), kredit=jumlah),
        ])
        utang.jurnal_reklasifikasi = header
        utang.save(update_fields=['jurnal_reklasifikasi'])
        _log_audit(utang, 'EDIT', user=user, notes=f'Jurnal reklasifikasi dibuat: {nomor}, Rp {jumlah}')


def reverse_reklasifikasi_journal(utang: UtangHeader, user=None) -> None:
    if not utang.jurnal_reklasifikasi_id:
        raise ValueError('Tidak ada jurnal reklasifikasi untuk dibatalkan.')
    with transaction.atomic():
        jurnal = utang.jurnal_reklasifikasi
        nomor = jurnal.nomor_transaksi
        log_jurnal_terhapus(jurnal, 'utang', None)
        jurnal.delete()
        utang.jurnal_reklasifikasi = None
        utang.save(update_fields=['jurnal_reklasifikasi'])
        _log_audit(utang, 'EDIT', user=user, notes=f'Jurnal reklasifikasi dibatalkan: {nomor}')


# ── Reports ───────────────────────────────────────────────────────────────────

def get_utang_per_subjek():
    return (
        UtangHeader.objects
        .filter(status__in=['open', 'partial', 'overdue'])
        .values('entitas_bisnis__id', 'entitas_bisnis__nama', 'kreditor', 'jenis_utang')
        .annotate(total_utang=Sum('total_amount'), total_bayar=Sum('pembayaran__jumlah'), jumlah_invoice=Count('id'))
        .order_by('-total_utang')
    )


def get_utang_per_group_akun():
    return (
        UtangDetail.objects
        .filter(utang_header__status__in=['open', 'partial', 'overdue'])
        .values('coa_utang_account__kode_akun', 'coa_utang_account__nama')
        .annotate(total=Sum('amount'))
        .order_by('coa_utang_account__kode_akun')
    )


def get_utang_aging():
    today = timezone.now().date()
    qs = (
        UtangHeader.objects
        .filter(status__in=['open', 'partial', 'overdue'], tanggal_jatuh_tempo__isnull=False)
        .select_related('entitas_bisnis', 'purchase_header')
        .annotate(total_bayar=Sum('pembayaran__jumlah'))
    )
    buckets = {
        'current': [], 'due_1_30': [], 'due_31_60': [],
        'due_61_90': [], 'due_91_180': [], 'due_180_plus': [],
    }
    for u in qs:
        delta = (today - u.tanggal_jatuh_tempo).days
        outstanding = u.total_amount - (u.total_bayar or Decimal('0'))
        entry = {'utang': u, 'outstanding': outstanding, 'hari': delta}
        if delta <= 0:
            buckets['current'].append(entry)
        elif delta <= 30:
            buckets['due_1_30'].append(entry)
        elif delta <= 60:
            buckets['due_31_60'].append(entry)
        elif delta <= 90:
            buckets['due_61_90'].append(entry)
        elif delta <= 180:
            buckets['due_91_180'].append(entry)
        else:
            buckets['due_180_plus'].append(entry)
    return buckets


def get_utang_jatuh_tempo(hari_ke_depan: int = 7):
    from datetime import timedelta
    batas = timezone.now().date() + timedelta(days=hari_ke_depan)
    return (
        UtangHeader.objects
        .filter(status__in=['open', 'partial', 'overdue'], tanggal_jatuh_tempo__isnull=False, tanggal_jatuh_tempo__lte=batas)
        .select_related('entitas_bisnis')
        .order_by('tanggal_jatuh_tempo')
    )


def get_utang_dashboard_kpi() -> dict:
    from datetime import timedelta
    from django.db.models import Q
    active_statuses = ['open', 'partial', 'overdue']
    qs = UtangHeader.objects.filter(status__in=active_statuses)
    total_outstanding = qs.aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    total_paid = UtangPembayaran.objects.filter(utang_header__in=qs).aggregate(total=Sum('jumlah'))['total'] or Decimal('0')
    sisa = total_outstanding - total_paid

    today = timezone.now().date()
    jatuh_tempo_7 = qs.filter(tanggal_jatuh_tempo__lte=today + timedelta(days=7), tanggal_jatuh_tempo__gte=today).count()
    jatuh_tempo_30 = qs.filter(tanggal_jatuh_tempo__lte=today + timedelta(days=30), tanggal_jatuh_tempo__gte=today).count()
    overdue_count = qs.filter(tanggal_jatuh_tempo__lt=today).count()

    by_jenis = (
        qs.values('jenis_utang')
        .annotate(total=Sum('total_amount'))
        .order_by('-total')
    )

    long_term_list = list(
        UtangHeader.objects
        .filter(status__in=active_statuses, kategori_jangka_waktu='long_term')
        .prefetch_related('pembayaran')
    )
    bagian_lancar_total = sum(compute_bagian_lancar(u)['bagian_lancar'] for u in long_term_list)

    return {
        'total_outstanding': total_outstanding,
        'total_paid': total_paid,
        'sisa': sisa,
        'jatuh_tempo_7': jatuh_tempo_7,
        'jatuh_tempo_30': jatuh_tempo_30,
        'overdue_count': overdue_count,
        'by_jenis': list(by_jenis),
        'waiting_approval': UtangHeader.objects.filter(status='waiting_approval').count(),
        'draft_count': UtangHeader.objects.filter(status='draft').count(),
        'bagian_lancar_total': bagian_lancar_total,
        'long_term_count': len(long_term_list),
    }
