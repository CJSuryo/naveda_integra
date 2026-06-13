from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.jurnal.models import JurnalDetail, JurnalHeader

from .models import (
    PiutangAuditLog, PiutangAttachment, PiutangDetail, PiutangHeader,
    PiutangPenerimaan, PiutangReklasifikasi, PiutangWriteOff,
)


# ── Schedule Helpers ──────────────────────────────────────────────────────────

_PERIODE_MONTHS_MAP = {'bulanan': 1, 'triwulanan': 3, 'semesteran': 6, 'tahunan': 12}


def _add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return d.replace(year=year, month=month, day=day)


def compute_angsuran_schedule(piutang) -> list:
    """Returns installment schedule for a PiutangHeader. Empty list if no jatuh_tempo."""
    if not piutang.jatuh_tempo:
        return []
    periode_months = _PERIODE_MONTHS_MAP.get(piutang.periode_angsuran, 1)
    total_months = (
        (piutang.jatuh_tempo.year - piutang.tanggal.year) * 12
        + (piutang.jatuh_tempo.month - piutang.tanggal.month)
    )
    if total_months <= 0:
        return []
    n = max(1, round(total_months / periode_months))
    total = float(piutang.jumlah_pokok)
    jenis = piutang.jenis_bunga
    r = float(piutang.suku_bunga) / 100 / 12 * periode_months if jenis != 'tanpa_bunga' else 0.0

    rows = []
    sisa = total
    if jenis == 'anuitas' and r > 0:
        pmt = total * r / (1 - (1 + r) ** (-n))
        for i in range(n):
            bunga_i = sisa * r
            pokok_i = pmt - bunga_i
            if i == n - 1:
                pokok_i = sisa
            angsuran_i = pokok_i + bunga_i
            sisa -= pokok_i
            rows.append({
                'no': i + 1,
                'tanggal': _add_months(piutang.tanggal, (i + 1) * periode_months),
                'pokok': Decimal(str(int(round(pokok_i, 0)))),
                'bunga': Decimal(str(int(round(bunga_i, 0)))),
                'angsuran': Decimal(str(int(round(angsuran_i, 0)))),
                'sisa_pokok': Decimal(str(int(round(max(0.0, sisa), 0)))),
            })
    else:
        pk_unit = round(total / n, 0)
        bng_unit = round(total * r, 0) if jenis == 'flat' else 0.0
        cumulative_pk = 0.0
        for i in range(n):
            pk_i = round(total - cumulative_pk, 0) if i == n - 1 else pk_unit
            cumulative_pk += pk_i
            sisa -= pk_i
            ang_i = pk_i + bng_unit
            rows.append({
                'no': i + 1,
                'tanggal': _add_months(piutang.tanggal, (i + 1) * periode_months),
                'pokok': Decimal(str(int(pk_i))),
                'bunga': Decimal(str(int(bng_unit))),
                'angsuran': Decimal(str(int(ang_i))),
                'sisa_pokok': Decimal(str(int(round(max(0.0, sisa), 0)))),
            })

    # Payment matching: direct via angsuran_no; unallocated pool fills in order
    direct_paid: dict[int, float] = {}
    unallocated = 0.0
    penerimaan_qs = piutang.penerimaan.all() if piutang.pk else []
    for p in penerimaan_qs:
        if p.angsuran_no:
            direct_paid[p.angsuran_no] = direct_paid.get(p.angsuran_no, 0.0) + float(p.jumlah_diterima)
        else:
            unallocated += float(p.jumlah_diterima)

    today = date.today()
    for row in rows:
        ang = float(row['angsuran'])
        no = row['no']
        paid = direct_paid.get(no, 0.0)
        if paid < ang - 1.0 and unallocated > 0:
            apply = min(unallocated, max(0.0, ang - paid))
            paid += apply
            unallocated = max(0.0, unallocated - apply)
        row['paid'] = Decimal(str(round(paid, 0)))
        row['sisa_bayar'] = Decimal(str(round(max(0.0, ang - paid), 0)))
        if paid >= ang - 1.0:
            row['status'] = 'lunas'
            row['sisa_bayar'] = Decimal('0')
        elif paid > 1.0:
            row['status'] = 'sebagian'
        elif row['tanggal'] < today:
            row['status'] = 'jatuh_tempo'
        else:
            row['status'] = 'akan_datang'
    return rows


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
    jenis_bunga: str = 'tanpa_bunga',
    suku_bunga: Decimal = Decimal('0'),
    periode_angsuran: str = 'bulanan',
    is_approval_required: bool = False,
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
            jenis_bunga=jenis_bunga,
            suku_bunga=suku_bunga,
            periode_angsuran=periode_angsuran,
            is_approval_required=is_approval_required,
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
    total = Decimal('0')
    details = []
    for eb_group in sales_header.entitas_groups.select_related('entitas_bisnis').all():
        for item in eb_group.items.select_related('revenue_account').all():
            total += item.total_sales
            details.append({
                'deskripsi': str(item.item),
                'jumlah': item.total_sales,
                'revenue_account': item.revenue_account,
            })

    if total <= 0:
        raise ValueError('Total credit sales harus lebih besar dari 0.')

    coa_piutang = (
        sales_header.entitas_groups.first().payment_account
        if sales_header.entitas_groups.exists()
        else None
    )
    if not coa_piutang:
        raise ValueError('Payment account (akun piutang) diperlukan pada SalesEntitasBisnis.')

    eb = sales_header.entitas_groups.first().entitas_bisnis if sales_header.entitas_groups.exists() else None

    with transaction.atomic():
        piutang = PiutangHeader.objects.create(
            tanggal=sales_header.tanggal,
            entitas_bisnis=eb,
            debitur=str(eb) if eb else '',
            deskripsi=f'Piutang dari Sales {sales_header.transaction_id}',
            source_type='from_sales',
            source_sales=sales_header,
            jumlah_pokok=total,
            status='open',
            coa_piutang_account=coa_piutang,
            created_by=user,
        )
        PiutangDetail.objects.bulk_create([
            PiutangDetail(
                piutang_header=piutang,
                deskripsi=d['deskripsi'],
                jumlah=d['jumlah'],
                revenue_account=d.get('revenue_account'),
            )
            for d in details
        ])
        _log(piutang, 'CREATED', user=user, after=_snapshot(piutang))
    return piutang


def create_piutang_from_pendapatan(pendapatan_header, user=None) -> PiutangHeader:
    total = Decimal('0')
    details = []
    for eb_group in pendapatan_header.entitas_groups.prefetch_related('items__revenue_account').all():
        for item in eb_group.items.all():
            total += item.jumlah_bruto
            details.append({
                'deskripsi': item.deskripsi_item[:255],
                'jumlah': item.jumlah_bruto,
                'revenue_account': item.revenue_account,
            })

    if total <= 0:
        raise ValueError('Total pendapatan kredit harus lebih besar dari 0.')

    coa_piutang = (
        pendapatan_header.entitas_groups.first().payment_account
        if pendapatan_header.entitas_groups.exists()
        else None
    )
    if not coa_piutang:
        raise ValueError('Payment account (akun piutang) diperlukan pada PendapatanEntitasBisnis.')

    eb = (
        pendapatan_header.entitas_groups.first().entitas_bisnis
        if pendapatan_header.entitas_groups.exists()
        else None
    )

    with transaction.atomic():
        piutang = PiutangHeader.objects.create(
            tanggal=pendapatan_header.tanggal,
            entitas_bisnis=eb,
            debitur=str(eb) if eb else '',
            deskripsi=f'Piutang dari Pendapatan {pendapatan_header.transaction_id}',
            source_type='from_pendapatan',
            source_pendapatan=pendapatan_header,
            jumlah_pokok=total,
            status='open',
            coa_piutang_account=coa_piutang,
            created_by=user,
        )
        PiutangDetail.objects.bulk_create([
            PiutangDetail(
                piutang_header=piutang,
                deskripsi=d['deskripsi'],
                jumlah=d['jumlah'],
                revenue_account=d.get('revenue_account'),
            )
            for d in details
        ])
        _log(piutang, 'CREATED', user=user, after=_snapshot(piutang))
    return piutang


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

        if piutang.status == 'paid':
            auto_reverse_penyisihan_on_payment(piutang, user=user)

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


def auto_reverse_penyisihan_on_payment(piutang: PiutangHeader, user=None) -> None:
    from .models import PiutangPenyisihan
    if piutang.status != 'paid':
        return
    entries = list(
        PiutangPenyisihan.objects.filter(piutang_header=piutang, jenis='manual')
        .select_related('jurnal_header')
    )
    for entry in entries:
        reverse_penyisihan_journal(entry, user=user)


def compute_bagian_lancar(piutang: PiutangHeader) -> Decimal:
    if not piutang.jatuh_tempo:
        return Decimal('0')
    today = timezone.now().date()
    cutoff = today.replace(year=today.year + 1)
    if piutang.jenis_jangka_waktu != 'long_term':
        return piutang.sisa_piutang if piutang.jatuh_tempo <= cutoff else Decimal('0')
    schedule = compute_angsuran_schedule(piutang)
    if not schedule:
        return piutang.sisa_piutang if piutang.jatuh_tempo <= cutoff else Decimal('0')
    return sum(
        (row['sisa_bayar'] for row in schedule if row['status'] != 'lunas' and row['tanggal'] <= cutoff),
        Decimal('0'),
    )


def create_reklasifikasi_bagian_lancar(
    piutang: PiutangHeader, dari_akun, ke_akun, tanggal, user=None,
) -> PiutangReklasifikasi:
    periode_bulan = tanggal.month
    periode_tahun = tanggal.year
    if PiutangReklasifikasi.objects.filter(
        piutang_header=piutang,
        periode_bulan=periode_bulan,
        periode_tahun=periode_tahun,
    ).exists():
        raise ValueError(
            f'Reklasifikasi bagian lancar untuk periode {periode_tahun}-{periode_bulan:02d} sudah ada.'
        )
    jumlah = compute_bagian_lancar(piutang)
    if jumlah <= 0:
        raise ValueError('Tidak ada bagian lancar yang dapat direklasifikasi.')
    with transaction.atomic():
        nomor = _next_piutang_journal_number('TRX-PIU-RKL')
        jurnal = JurnalHeader.objects.create(
            tanggal=tanggal,
            nomor_transaksi=nomor,
            uraian_transaksi=f'Reklasifikasi Bagian Lancar {piutang.nomor_piutang}',
            entitas_bisnis=piutang.entitas_bisnis,
            is_penyesuaian=False,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(jurnal_header=jurnal, akun=dari_akun, debit=Decimal('0'), kredit=jumlah),
            JurnalDetail(jurnal_header=jurnal, akun=ke_akun, debit=jumlah, kredit=Decimal('0')),
        ])
        rkl = PiutangReklasifikasi.objects.create(
            piutang_header=piutang,
            tanggal=tanggal,
            dari_akun=dari_akun,
            ke_akun=ke_akun,
            jumlah=jumlah,
            keterangan=f'Bagian lancar {periode_tahun}-{periode_bulan:02d}',
            jurnal=jurnal,
            periode_bulan=periode_bulan,
            periode_tahun=periode_tahun,
            created_by=user,
        )
        _log(piutang, 'REKLASIFIKASI', user=user, after={'jumlah': str(jumlah)})
    return rkl


def write_off_piutang(piutang: PiutangHeader, data: dict, user=None) -> PiutangWriteOff:
    with transaction.atomic():
        jumlah = piutang.sisa_piutang
        nomor = _next_piutang_journal_number('TRX-PIU-WO')
        metode = data['metode']
        bad_debt = data['bad_debt_account']
        allowance = data.get('allowance_account')

        dr_akun = allowance if metode == 'cadangan' and allowance else bad_debt

        header = JurnalHeader.objects.create(
            tanggal=data['tanggal'],
            nomor_transaksi=nomor,
            uraian_transaksi=f'Write-Off Piutang {piutang.nomor_piutang}',
            entitas_bisnis=piutang.entitas_bisnis,
            is_penyesuaian=False,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(jurnal_header=header, akun=dr_akun, debit=jumlah, kredit=Decimal('0')),
            JurnalDetail(jurnal_header=header, akun=piutang.coa_piutang_account, debit=Decimal('0'), kredit=jumlah),
        ])

        wo = PiutangWriteOff.objects.create(
            piutang_header=piutang,
            tanggal=data['tanggal'],
            jumlah_dihapus=jumlah,
            metode=metode,
            bad_debt_account=bad_debt,
            allowance_account=allowance,
            alasan=data.get('alasan', ''),
            jurnal=header,
            created_by=user,
        )
        piutang.status = 'written_off'
        piutang.is_locked = True
        piutang.save(update_fields=['status', 'is_locked'])
        _log(piutang, 'WRITE_OFF', user=user, after=_snapshot(piutang))
    return wo


def reverse_piutang_payment(penerimaan: PiutangPenerimaan, user=None) -> JurnalHeader:
    with transaction.atomic():
        piutang = PiutangHeader.objects.select_for_update().get(pk=penerimaan.piutang_header_id)
        orig = penerimaan.jurnal_header
        nomor = _next_piutang_journal_number('TRX-PIU-PR')
        rev_header = JurnalHeader.objects.create(
            tanggal=timezone.now().date(),
            nomor_transaksi=nomor,
            uraian_transaksi=f'Reversal Penerimaan {piutang.nomor_piutang}',
            entitas_bisnis=piutang.entitas_bisnis,
            is_penyesuaian=True,
        )
        if orig:
            JurnalDetail.objects.bulk_create([
                JurnalDetail(
                    jurnal_header=rev_header,
                    akun=d.akun,
                    debit=d.kredit,
                    kredit=d.debit,
                )
                for d in orig.details.all()
            ])

        penerimaan.delete()

        total_paid = piutang.penerimaan.aggregate(s=Sum('jumlah_diterima'))['s'] or Decimal('0')
        piutang.jumlah_terbayar = total_paid
        if total_paid <= 0:
            if piutang.status not in ('draft', 'cancelled', 'written_off'):
                piutang.status = 'open'
        elif total_paid < piutang.jumlah_pokok:
            piutang.status = 'partial'
        piutang.save(update_fields=['jumlah_terbayar', 'status'])
        _log(piutang, 'REVERSE_PAYMENT', user=user, after=_snapshot(piutang))
    return rev_header


_AGING_BUCKET_KEYS = ['current', '1_30', '31_60', '61_90', '91_180', '181_365', 'over_365']
_AGING_BUCKET_LABELS = {
    'current':  'Belum Jatuh Tempo',
    '1_30':     'Lewat 1–30 Hari',
    '31_60':    'Lewat 31–60 Hari',
    '61_90':    'Lewat 61–90 Hari',
    '91_180':   'Lewat 91–180 Hari',
    '181_365':  'Lewat 181–365 Hari',
    'over_365': 'Lewat > 365 Hari',
}


def _classify_bucket(tanggal, today) -> str:
    if tanggal is None:
        return 'current'
    delta = (today - tanggal).days
    if delta <= 0:
        return 'current'
    elif delta <= 30:
        return '1_30'
    elif delta <= 60:
        return '31_60'
    elif delta <= 90:
        return '61_90'
    elif delta <= 180:
        return '91_180'
    elif delta <= 365:
        return '181_365'
    else:
        return 'over_365'


def get_piutang_aging() -> dict:
    today = timezone.now().date()
    buckets = {k: [] for k in _AGING_BUCKET_KEYS}
    qs = (
        PiutangHeader.objects
        .filter(status__in=('open', 'partial', 'overdue'))
        .select_related('entitas_bisnis')
        .prefetch_related('penerimaan')
    )
    for piutang in qs:
        if piutang.jenis_jangka_waktu == 'long_term' and piutang.jatuh_tempo:
            schedule = compute_angsuran_schedule(piutang)
            if schedule:
                for row in schedule:
                    if row['status'] != 'lunas' and row['sisa_bayar'] > 0:
                        key = _classify_bucket(row['tanggal'], today)
                        buckets[key].append({
                            'piutang': piutang,
                            'angsuran_no': row['no'],
                            'tanggal_angsuran': row['tanggal'],
                            'jumlah': row['sisa_bayar'],
                            'hari_lewat': max(0, (today - row['tanggal']).days),
                        })
                continue
        key = _classify_bucket(piutang.jatuh_tempo, today)
        buckets[key].append({
            'piutang': piutang,
            'angsuran_no': None,
            'tanggal_angsuran': piutang.jatuh_tempo,
            'jumlah': piutang.sisa_piutang,
            'hari_lewat': max(0, (today - piutang.jatuh_tempo).days) if piutang.jatuh_tempo else 0,
        })
    return buckets


def get_aging_schedule_report(as_of_date=None) -> dict:
    today = as_of_date or date.today()
    short_term_rows = []
    long_term_rows = []

    qs = (
        PiutangHeader.objects
        .filter(status__in=('open', 'partial', 'overdue'))
        .select_related('entitas_bisnis')
        .prefetch_related('penerimaan')
    )
    for piutang in qs:
        if piutang.jenis_jangka_waktu == 'long_term' and piutang.jatuh_tempo:
            schedule = compute_angsuran_schedule(piutang)
            if schedule:
                for row in schedule:
                    if row['status'] != 'lunas' and row['sisa_bayar'] > 0:
                        bucket_key = _classify_bucket(row['tanggal'], today)
                        long_term_rows.append({
                            'nomor_piutang': piutang.nomor_piutang,
                            'debitur': piutang.entitas_display,
                            'tanggal': piutang.tanggal,
                            'jatuh_tempo_efektif': row['tanggal'],
                            'jumlah_piutang': row['sisa_bayar'],
                            'bucket_key': bucket_key,
                            'bucket_label': _AGING_BUCKET_LABELS[bucket_key],
                            'hari_lewat': max(0, (today - row['tanggal']).days),
                            'angsuran_no': row['no'],
                            'piutang_pk': piutang.pk,
                        })
                continue
        bucket_key = _classify_bucket(piutang.jatuh_tempo, today)
        short_term_rows.append({
            'nomor_piutang': piutang.nomor_piutang,
            'debitur': piutang.entitas_display,
            'tanggal': piutang.tanggal,
            'jatuh_tempo_efektif': piutang.jatuh_tempo,
            'jumlah_piutang': piutang.sisa_piutang,
            'bucket_key': bucket_key,
            'bucket_label': _AGING_BUCKET_LABELS[bucket_key],
            'hari_lewat': max(0, (today - piutang.jatuh_tempo).days) if piutang.jatuh_tempo else 0,
            'angsuran_no': None,
            'piutang_pk': piutang.pk,
        })

    def _section(rows):
        bucket_totals = {k: Decimal('0') for k in _AGING_BUCKET_KEYS}
        for r in rows:
            bucket_totals[r['bucket_key']] += r['jumlah_piutang']
        return {
            'rows': rows,
            'bucket_totals': bucket_totals,
            'grand_total': sum(bucket_totals.values()),
        }

    st = _section(short_term_rows)
    lt = _section(long_term_rows)
    combined = {k: st['bucket_totals'][k] + lt['bucket_totals'][k] for k in _AGING_BUCKET_KEYS}
    return {
        'as_of_date': today,
        'short_term': st,
        'long_term': lt,
        'combined_bucket_totals': combined,
        'grand_total': sum(combined.values()),
    }


def get_aging_schedule_workbook(report_data: dict):
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    bucket_labels_ordered = [_AGING_BUCKET_LABELS[k] for k in _AGING_BUCKET_KEYS]
    header_row = (
        ['No Piutang', 'Debitur', 'Tanggal', 'Jatuh Tempo Efektif', 'No Angsuran', 'Total']
        + bucket_labels_ordered
    )
    bold = Font(bold=True)
    fill = PatternFill(start_color='DDEEFF', end_color='DDEEFF', fill_type='solid')

    for section_key, sheet_name in (('short_term', 'Jangka Pendek'), ('long_term', 'Jangka Panjang')):
        ws = wb.create_sheet(title=sheet_name)
        ws.append(header_row)
        for cell in ws[1]:
            cell.font = bold
            cell.fill = fill

        section = report_data[section_key]
        for row in section['rows']:
            ws.append([
                row['nomor_piutang'],
                row['debitur'],
                row['tanggal'].isoformat() if row['tanggal'] else '',
                row['jatuh_tempo_efektif'].isoformat() if row['jatuh_tempo_efektif'] else '',
                row['angsuran_no'] or '',
                float(row['jumlah_piutang']),
            ] + [
                float(row['jumlah_piutang']) if row['bucket_key'] == k else 0
                for k in _AGING_BUCKET_KEYS
            ])

        totals_row = ['', '', '', '', 'TOTAL', float(section['grand_total'])] + [
            float(section['bucket_totals'][k]) for k in _AGING_BUCKET_KEYS
        ]
        ws.append(totals_row)
        for cell in ws[ws.max_row]:
            cell.font = bold

    return wb


def _get_rate_config() -> dict:
    from .models import PenyisihanRateConfig
    return {r.bucket_key: r.rate_percent for r in PenyisihanRateConfig.objects.all()}


def compute_penyisihan_for_piutang(piutang) -> dict:
    rates = _get_rate_config()
    today = date.today()
    bucket_amounts = {k: Decimal('0') for k in _AGING_BUCKET_KEYS}

    if piutang.jenis_jangka_waktu == 'long_term' and piutang.jatuh_tempo:
        schedule = compute_angsuran_schedule(piutang)
        if schedule:
            for row in schedule:
                if row['status'] != 'lunas' and row['sisa_bayar'] > 0:
                    key = _classify_bucket(row['tanggal'], today)
                    bucket_amounts[key] += row['sisa_bayar']
        else:
            key = _classify_bucket(piutang.jatuh_tempo, today)
            bucket_amounts[key] += piutang.sisa_piutang
    else:
        key = _classify_bucket(piutang.jatuh_tempo, today)
        bucket_amounts[key] += piutang.sisa_piutang

    breakdown = []
    total = Decimal('0')
    for key in _AGING_BUCKET_KEYS:
        amt = bucket_amounts[key]
        rate = rates.get(key, Decimal('0'))
        penyisihan = (amt * rate / 100).quantize(Decimal('0.01'))
        total += penyisihan
        breakdown.append({
            'bucket_key': key,
            'label': _AGING_BUCKET_LABELS[key],
            'jumlah_piutang': amt,
            'rate': rate,
            'penyisihan': penyisihan,
        })
    return {'total_penyisihan': total, 'breakdown': breakdown}


def _next_penyisihan_journal_number(prefix='TRX-PIU-PSH') -> str:
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


def create_penyisihan_journal(
    piutang, allowance_account, expense_account, tanggal, catatan='', user=None
):
    from .models import PiutangPenyisihan
    piutang_pk = piutang.pk
    with transaction.atomic():
        piutang = PiutangHeader.objects.select_for_update().get(pk=piutang_pk)
        result = compute_penyisihan_for_piutang(piutang)
        total = result['total_penyisihan']
        if total <= 0:
            raise ValueError('Tidak ada penyisihan yang dapat dihitung untuk piutang ini.')
        nomor = _next_penyisihan_journal_number('TRX-PIU-PSH')
        header = JurnalHeader.objects.create(
            tanggal=tanggal,
            nomor_transaksi=nomor,
            uraian_transaksi=f'Penyisihan Piutang {piutang.nomor_piutang}',
            entitas_bisnis=piutang.entitas_bisnis,
            is_penyesuaian=True,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(jurnal_header=header, akun=expense_account, debit=total, kredit=Decimal('0')),
            JurnalDetail(jurnal_header=header, akun=allowance_account, debit=Decimal('0'), kredit=total),
        ])
        entry = PiutangPenyisihan.objects.create(
            piutang_header=piutang,
            tanggal=tanggal,
            jenis='manual',
            jumlah=total,
            allowance_account=allowance_account,
            expense_account=expense_account,
            jurnal_header=header,
            catatan=catatan,
            created_by=user,
        )
        piutang.is_specifically_impaired = True
        piutang.save(update_fields=['is_specifically_impaired'])
        _log(piutang, 'PENYISIHAN', user=user, after={'jumlah': str(total), 'nomor': nomor})
    return entry


def reverse_penyisihan_journal(entry, user=None) -> None:
    from .models import PiutangPenyisihan
    piutang = entry.piutang_header
    with transaction.atomic():
        if entry.jurnal_header_id:
            orig = entry.jurnal_header
            nomor = _next_penyisihan_journal_number('TRX-PIU-PSHR')
            rev = JurnalHeader.objects.create(
                tanggal=timezone.now().date(),
                nomor_transaksi=nomor,
                uraian_transaksi=f'Reversal Penyisihan {piutang.nomor_piutang if piutang else ""}',
                entitas_bisnis=piutang.entitas_bisnis if piutang else None,
                is_penyesuaian=True,
            )
            JurnalDetail.objects.bulk_create([
                JurnalDetail(jurnal_header=rev, akun=d.akun, debit=d.kredit, kredit=d.debit)
                for d in orig.details.all()
            ])
        entry.delete()
        if piutang:
            remaining = PiutangPenyisihan.objects.filter(
                piutang_header=piutang, jenis='manual'
            ).exists()
            if not remaining:
                piutang.is_specifically_impaired = False
                piutang.save(update_fields=['is_specifically_impaired'])
            _log(piutang, 'PENYISIHAN', user=user, notes='Jurnal penyisihan dibatalkan')


def update_penyisihan_individual(
    existing_entry, allowance_account, expense_account, tanggal, catatan='', user=None,
):
    piutang = existing_entry.piutang_header
    with transaction.atomic():
        reverse_penyisihan_journal(existing_entry, user=user)
        new_entry = create_penyisihan_journal(
            piutang=piutang,
            allowance_account=allowance_account,
            expense_account=expense_account,
            tanggal=tanggal,
            catatan=catatan,
            user=user,
        )
    return new_entry


def compute_batch_penyisihan(tanggal, allowance_account) -> dict:
    rates = _get_rate_config()
    today = tanggal  # caller-supplied date used as "today" for aging classification
    bucket_amounts = {k: Decimal('0') for k in _AGING_BUCKET_KEYS}
    piutang_count = 0

    qs = (
        PiutangHeader.objects
        .filter(status__in=('open', 'partial', 'overdue'), is_specifically_impaired=False)
        .prefetch_related('penerimaan')
    )
    for piutang in qs:
        piutang_count += 1
        if piutang.jenis_jangka_waktu == 'long_term' and piutang.jatuh_tempo:
            schedule = compute_angsuran_schedule(piutang)
            if schedule:
                for row in schedule:
                    if row['status'] != 'lunas' and row['sisa_bayar'] > 0:
                        key = _classify_bucket(row['tanggal'], today)
                        bucket_amounts[key] += row['sisa_bayar']
                continue
        key = _classify_bucket(piutang.jatuh_tempo, today)
        bucket_amounts[key] += piutang.sisa_piutang

    breakdown = []
    target_saldo = Decimal('0')
    for key in _AGING_BUCKET_KEYS:
        amt = bucket_amounts[key]
        rate = rates.get(key, Decimal('0'))
        penyisihan = (amt * rate / 100).quantize(Decimal('0.01'))
        target_saldo += penyisihan
        breakdown.append({
            'bucket_key': key,
            'label': _AGING_BUCKET_LABELS[key],
            'jumlah_piutang': amt,
            'rate': rate,
            'penyisihan': penyisihan,
        })

    from .models import PiutangPenyisihan as _PP
    saldo_existing = (
        _PP.objects
        .filter(jenis='batch', tanggal__lte=tanggal)
        .aggregate(s=Sum('jumlah'))['s'] or Decimal('0')
    )
    saldo_existing = Decimal(str(saldo_existing)).quantize(Decimal('0.01'))

    delta = (target_saldo - saldo_existing).quantize(Decimal('0.01'))
    return {
        'target_saldo': target_saldo,
        'saldo_existing': saldo_existing,
        'delta': delta,
        'breakdown': breakdown,
        'piutang_count': piutang_count,
    }


def create_batch_penyisihan_journal(
    batch_data: dict, allowance_account, expense_account,
    tanggal, catatan='', periode_label='', user=None,
):
    from .models import PiutangPenyisihan
    delta = batch_data['delta']
    if delta == 0:
        raise ValueError('Delta penyisihan adalah 0, tidak perlu jurnal.')
    if periode_label and PiutangPenyisihan.objects.filter(
        jenis='batch', periode_label=periode_label
    ).exists():
        raise ValueError(
            f'Jurnal penyisihan batch untuk periode {periode_label} sudah ada.'
        )
    with transaction.atomic():
        nomor = _next_penyisihan_journal_number('TRX-PIU-PSH-B')
        header = JurnalHeader.objects.create(
            tanggal=tanggal,
            nomor_transaksi=nomor,
            uraian_transaksi=f'Penyisihan Piutang Batch — {tanggal}',
            is_penyesuaian=True,
        )
        abs_delta = abs(delta)
        if delta > 0:
            JurnalDetail.objects.bulk_create([
                JurnalDetail(jurnal_header=header, akun=expense_account, debit=abs_delta, kredit=Decimal('0')),
                JurnalDetail(jurnal_header=header, akun=allowance_account, debit=Decimal('0'), kredit=abs_delta),
            ])
        else:
            JurnalDetail.objects.bulk_create([
                JurnalDetail(jurnal_header=header, akun=allowance_account, debit=abs_delta, kredit=Decimal('0')),
                JurnalDetail(jurnal_header=header, akun=expense_account, debit=Decimal('0'), kredit=abs_delta),
            ])
        entry = PiutangPenyisihan.objects.create(
            piutang_header=None,
            tanggal=tanggal,
            jenis='batch',
            jumlah=delta,
            allowance_account=allowance_account,
            expense_account=expense_account,
            jurnal_header=header,
            catatan=catatan,
            periode_label=periode_label,
            created_by=user,
        )
    return entry


def get_piutang_dashboard_kpi() -> dict:
    today = timezone.now().date()
    month_start = today.replace(day=1)
    outstanding_qs = PiutangHeader.objects.filter(status__in=('open', 'partial', 'overdue'))
    total_outstanding = outstanding_qs.aggregate(s=Sum('jumlah_pokok'))['s'] or Decimal('0')
    total_terbayar = outstanding_qs.aggregate(s=Sum('jumlah_terbayar'))['s'] or Decimal('0')
    total_outstanding -= total_terbayar

    overdue_qs = outstanding_qs.filter(jatuh_tempo__lt=today)
    total_overdue = sum(p.sisa_piutang for p in overdue_qs)

    collected_this_month = (
        PiutangPenerimaan.objects
        .filter(tanggal_terima__gte=month_start)
        .aggregate(s=Sum('jumlah_diterima'))['s'] or Decimal('0')
    )
    collection_rate = (
        collected_this_month / (collected_this_month + total_outstanding) * 100
        if (collected_this_month + total_outstanding) > 0 else Decimal('0')
    )

    aging_buckets = get_piutang_aging()
    rates = _get_rate_config()
    aging_summary = {}
    total_penyisihan_target = Decimal('0')
    for key in _AGING_BUCKET_KEYS:
        total_amt = sum(entry['jumlah'] for entry in aging_buckets[key])
        rate = rates.get(key, Decimal('0'))
        penyisihan = (Decimal(str(total_amt)) * rate / 100).quantize(Decimal('0.01'))
        total_penyisihan_target += penyisihan
        aging_summary[key] = {
            'label': _AGING_BUCKET_LABELS[key],
            'total_outstanding': Decimal(str(total_amt)),
            'rate': rate,
            'penyisihan': penyisihan,
        }
    total_penyisihan_target = total_penyisihan_target.quantize(Decimal('0.01'))
    piutang_neto = (total_outstanding - total_penyisihan_target).quantize(Decimal('0.01'))

    return {
        'total_outstanding': total_outstanding,
        'total_overdue': total_overdue,
        'collected_this_month': collected_this_month,
        'collection_rate': collection_rate.quantize(Decimal('0.01')),
        'total_penyisihan_target': total_penyisihan_target,
        'piutang_neto': piutang_neto,
        'aging_summary': aging_summary,
    }


def get_piutang_disclosure_report(as_of_date=None) -> dict:
    from .models import PiutangPenyisihan
    today = as_of_date or date.today()
    year_start = today.replace(month=1, day=1)

    outstanding_list = list(
        PiutangHeader.objects
        .filter(status__in=('open', 'partial', 'overdue'))
        .select_related('entitas_bisnis')
    )
    total_outstanding = sum(p.sisa_piutang for p in outstanding_list)

    short_term_total = sum(p.sisa_piutang for p in outstanding_list if p.jenis_jangka_waktu == 'short_term')
    long_term_total = sum(p.sisa_piutang for p in outstanding_list if p.jenis_jangka_waktu == 'long_term')

    penyisihan_opening = (
        PiutangPenyisihan.objects.filter(tanggal__lt=year_start)
        .aggregate(s=Sum('jumlah'))['s'] or Decimal('0')
    )
    penyisihan_ytd_pos = (
        PiutangPenyisihan.objects
        .filter(tanggal__gte=year_start, tanggal__lte=today, jumlah__gt=0)
        .aggregate(s=Sum('jumlah'))['s'] or Decimal('0')
    )
    penyisihan_ytd_neg = abs(
        PiutangPenyisihan.objects
        .filter(tanggal__gte=year_start, tanggal__lte=today, jumlah__lt=0)
        .aggregate(s=Sum('jumlah'))['s'] or Decimal('0')
    )
    total_penyisihan = (
        PiutangPenyisihan.objects.filter(tanggal__lte=today)
        .aggregate(s=Sum('jumlah'))['s'] or Decimal('0')
    )

    # Write-off total — adapt if PiutangWriteOff doesn't exist
    try:
        write_off_total = (
            PiutangWriteOff.objects.filter(tanggal__gte=year_start, tanggal__lte=today)
            .aggregate(s=Sum('jumlah_dihapus'))['s'] or Decimal('0')
        )
    except Exception:
        write_off_total = Decimal('0')

    # Impaired piutang — adapt if field doesn't exist
    try:
        impaired = [p for p in outstanding_list if p.is_specifically_impaired]
    except AttributeError:
        impaired = []
    impaired_total = sum(p.sisa_piutang for p in impaired)

    concentration = sorted(
        [{'debitur': p.entitas_display, 'outstanding': p.sisa_piutang} for p in outstanding_list],
        key=lambda x: x['outstanding'], reverse=True,
    )[:10]
    for item in concentration:
        item['pct'] = (
            (item['outstanding'] / total_outstanding * 100).quantize(Decimal('0.01'))
            if total_outstanding else Decimal('0')
        )

    rates = _get_rate_config()
    aging_buckets = get_piutang_aging()
    aging_summary = []
    for key in _AGING_BUCKET_KEYS:
        bucket_total = sum(Decimal(str(e['jumlah'])) for e in aging_buckets[key])
        rate = rates.get(key, Decimal('0'))
        aging_summary.append({
            'bucket_key': key,
            'label': _AGING_BUCKET_LABELS[key],
            'total': bucket_total,
            'rate': rate,
            'penyisihan': (bucket_total * rate / 100).quantize(Decimal('0.01')),
        })

    return {
        'as_of_date': today,
        'total_outstanding': total_outstanding,
        'short_term_total': short_term_total,
        'long_term_total': long_term_total,
        'total_penyisihan': total_penyisihan,
        'piutang_neto': total_outstanding - total_penyisihan,
        'allowance_reconciliation': {
            'opening': penyisihan_opening,
            'additions': penyisihan_ytd_pos,
            'reversals': penyisihan_ytd_neg,
            'write_offs': write_off_total,
            'closing': penyisihan_opening + penyisihan_ytd_pos - penyisihan_ytd_neg,
        },
        'impaired_count': len(impaired),
        'impaired_total': impaired_total,
        'concentration': concentration,
        'aging_summary': aging_summary,
    }


# ── Present Value Functions ───────────────────────────────────────────────────

def compute_present_value(piutang: PiutangHeader, market_rate: Decimal) -> Decimal:
    """Compute PV of all future cash flows discounted at market_rate (% per year).

    At 0% the result equals the sum of angsuran (== jumlah_pokok for tanpa_bunga).
    """
    schedule = compute_angsuran_schedule(piutang)
    if not schedule:
        return piutang.jumlah_pokok
    if market_rate == 0:
        total = sum(Decimal(str(row['angsuran'])) for row in schedule)
        return total
    periode_months = _PERIODE_MONTHS_MAP.get(getattr(piutang, 'periode_angsuran', 'bulanan'), 1)
    r_per_period = float(market_rate) / 100 / 12 * periode_months
    pv = Decimal('0')
    for row in schedule:
        n = row['no']
        cf = float(row['angsuran'])
        pv += Decimal(str(round(cf / ((1 + r_per_period) ** n), 4)))
    return pv.quantize(Decimal('0.0001'))


def _create_piutang_ar_journal(piutang: PiutangHeader) -> JurnalHeader:
    details = list(piutang.details.select_related('revenue_account').all())
    missing = [d.deskripsi or str(d.pk) for d in details if not d.revenue_account_id]
    if missing:
        raise ValueError(
            f'Akun pendapatan belum diisi untuk detail: {", ".join(missing)}. '
            'Isi akun pendapatan di setiap baris detail sebelum posting.'
        )
    nomor = _next_piutang_journal_number('TRX-PIU-POST')
    header = JurnalHeader.objects.create(
        tanggal=piutang.tanggal,
        nomor_transaksi=nomor,
        uraian_transaksi=f'Pengakuan Piutang {piutang.nomor_piutang}',
        entitas_bisnis=piutang.entitas_bisnis,
        is_penyesuaian=False,
    )
    JurnalDetail.objects.create(
        jurnal_header=header,
        akun=piutang.coa_piutang_account,
        debit=piutang.jumlah_pokok,
        kredit=Decimal('0'),
    )
    JurnalDetail.objects.bulk_create([
        JurnalDetail(
            jurnal_header=header,
            akun=detail.revenue_account,
            debit=Decimal('0'),
            kredit=detail.jumlah,
        )
        for detail in details
    ])
    return header


def post_piutang(piutang: PiutangHeader, user=None) -> JurnalHeader:
    with transaction.atomic():
        piutang = PiutangHeader.objects.select_for_update().get(pk=piutang.pk)
        if piutang.status != 'draft':
            raise ValueError(
                f'Hanya piutang berstatus draft yang dapat di-post. Status saat ini: {piutang.get_status_display()}.'
            )
        jurnal = _create_piutang_ar_journal(piutang)
        piutang.status = 'open'
        piutang.is_locked = True
        piutang.save(update_fields=['status', 'is_locked'])
        _log(piutang, 'POSTED', user=user, after={'status': 'open', 'jurnal': jurnal.nomor_transaksi})
    return jurnal


def submit_for_approval(piutang: PiutangHeader, user=None) -> None:
    with transaction.atomic():
        piutang = PiutangHeader.objects.select_for_update().get(pk=piutang.pk)
        if piutang.status != 'draft':
            raise ValueError('Hanya piutang berstatus draft yang dapat disubmit untuk approval.')
        piutang.status = 'pending_approval'
        piutang.save(update_fields=['status'])
        _log(piutang, 'SUBMITTED', user=user, after={'status': 'pending_approval'})


def approve_piutang(piutang: PiutangHeader, user=None) -> JurnalHeader:
    with transaction.atomic():
        piutang = PiutangHeader.objects.select_for_update().get(pk=piutang.pk)
        if piutang.status != 'pending_approval':
            raise ValueError('Hanya piutang berstatus pending_approval yang dapat disetujui.')
        jurnal = _create_piutang_ar_journal(piutang)
        piutang.status = 'open'
        piutang.is_locked = True
        piutang.approved_by = user
        piutang.approved_at = timezone.now()
        piutang.save(update_fields=['status', 'is_locked', 'approved_by', 'approved_at'])
        _log(piutang, 'APPROVED', user=user, after={'status': 'open', 'jurnal': jurnal.nomor_transaksi})
    return jurnal


def reject_piutang(piutang: PiutangHeader, user=None, alasan: str = '') -> None:
    with transaction.atomic():
        piutang = PiutangHeader.objects.select_for_update().get(pk=piutang.pk)
        if piutang.status != 'pending_approval':
            raise ValueError('Hanya piutang berstatus pending_approval yang dapat ditolak.')
        piutang.status = 'draft'
        piutang.save(update_fields=['status'])
        _log(piutang, 'REJECTED', user=user, after={'status': 'draft', 'alasan': alasan})


def compute_amortization_schedule_pv(piutang: PiutangHeader) -> list:
    """Effective-interest amortization table using nilai_wajar_awal and pv_discount_rate."""
    if not piutang.nilai_wajar_awal or not piutang.pv_discount_rate:
        return []
    schedule = compute_angsuran_schedule(piutang)
    if not schedule:
        return []
    periode_months = _PERIODE_MONTHS_MAP.get(getattr(piutang, 'periode_angsuran', 'bulanan'), 1)
    r_per_period = float(piutang.pv_discount_rate) / 100 / 12 * periode_months
    carrying = float(piutang.nilai_wajar_awal)
    rows = []
    for row in schedule:
        bunga_efektif = carrying * r_per_period
        cf = float(row['angsuran'])
        carrying = carrying * (1 + r_per_period) - cf
        rows.append({
            'periode': row['no'],
            'tanggal': row['tanggal'],
            'bunga_efektif': Decimal(str(round(bunga_efektif, 4))),
            'cash_flow': row['angsuran'],
            'carrying_value': Decimal(str(round(max(0.0, carrying), 4))),
        })
    return rows


def create_pv_adjustment_journal(
    piutang: PiutangHeader,
    interest_income_account,
    tanggal,
    periode_no: int,
    catatan='',
    user=None,
) -> JurnalHeader:
    """Create an amortization journal entry for a single PV discount period."""
    amort = compute_amortization_schedule_pv(piutang)
    if not amort or periode_no < 1 or periode_no > len(amort):
        raise ValueError(f'Periode {periode_no} tidak valid.')
    row = amort[periode_no - 1]
    bunga = row['bunga_efektif']
    if bunga <= 0:
        raise ValueError('Bunga efektif nol, tidak perlu jurnal.')
    with transaction.atomic():
        nomor = _next_piutang_journal_number('TRX-PIU-PV')
        header = JurnalHeader.objects.create(
            tanggal=tanggal,
            nomor_transaksi=nomor,
            uraian_transaksi=(
                f'Amortisasi PV Piutang {piutang.nomor_piutang} — Periode {periode_no}'
            ),
            entitas_bisnis=piutang.entitas_bisnis,
            is_penyesuaian=True,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(
                jurnal_header=header,
                akun=piutang.coa_piutang_account,
                debit=bunga,
                kredit=Decimal('0'),
            ),
            JurnalDetail(
                jurnal_header=header,
                akun=interest_income_account,
                debit=Decimal('0'),
                kredit=bunga,
            ),
        ])
        _log(
            piutang, 'EDITED', user=user,
            after={'pv_amortisasi': str(bunga), 'periode': periode_no},
        )
    return header
