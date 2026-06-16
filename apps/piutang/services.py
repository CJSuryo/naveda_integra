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
    pv_discount_rate=None,
    deferred_income_account=None,
    interest_income_account=None,
    coa_piutang_lancar_account=None,
    deferred_income_lancar_account=None,
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
            pv_discount_rate=pv_discount_rate,
            deferred_income_account=deferred_income_account,
            interest_income_account=interest_income_account,
            coa_piutang_lancar_account=coa_piutang_lancar_account,
            deferred_income_lancar_account=deferred_income_lancar_account,
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

def _piutang_journal_ids(piutang) -> set:
    """
    Collect all JurnalHeader PKs that belong to this piutang.

    Uses FK relationships where they exist (penerimaan, reklasifikasi, write-off)
    and falls back to safe uraian patterns only when no FK is available.
    All uraian-based patterns use the full nomor followed by a non-digit character
    (' —' or end-of-string) to prevent PIU-001 from matching PIU-0010.
    """
    from django.db.models import Q
    nom = piutang.nomor_piutang
    ids: set = set()

    # FK-linked: penerimaan (payment) journals
    ids.update(
        piutang.penerimaan.filter(jurnal_header__isnull=False)
        .values_list('jurnal_header_id', flat=True)
    )

    # FK-linked: reklasifikasi journals; collect PKs for reversal lookup too
    rkl_pks = []
    for rkl_pk, j_pk in piutang.reklasifikasi_entries.filter(
        jurnal__isnull=False
    ).values_list('pk', 'jurnal_id'):
        ids.add(j_pk)
        rkl_pks.append(rkl_pk)

    # Reklasifikasi reversal journals: deterministic nomor_transaksi TRX-PIU-RKLR-{pk}
    if rkl_pks:
        ids.update(
            JurnalHeader.objects.filter(
                nomor_transaksi__in=[f'TRX-PIU-RKLR-{pk}' for pk in rkl_pks]
            ).values_list('pk', flat=True)
        )

    # Uraian-based journals (no FK available).
    # Each pattern is anchored so that nom is not a bare prefix of a longer nomor:
    # - exact match (=) for uraian where nom is at the END
    # - startswith with ' —' suffix guard for uraian where nom is followed by extra text
    ids.update(
        JurnalHeader.objects.filter(
            Q(uraian_transaksi=f'Pengakuan Piutang {nom}') |
            Q(uraian_transaksi=f'Write-Off Piutang {nom}') |
            Q(uraian_transaksi=f'Reversal Penerimaan {nom}') |
            Q(uraian_transaksi__startswith=f'Penerimaan Piutang {nom} —') |
            Q(uraian_transaksi__startswith=f'Amortisasi PV Piutang {nom} —') |
            Q(uraian_transaksi__startswith=f'Akrual PV Piutang {nom} —') |
            Q(uraian_transaksi__startswith=f'Balik Akrual PV Piutang {nom} —')
        ).values_list('pk', flat=True)
    )

    return ids


def _net_debit_balance_for_piutang(account, piutang) -> Decimal:
    """
    Net debit balance on `account` across all journals for this piutang.
    Positive = normal asset balance; negative = net credit (normal for contra-assets).

    Collects journal IDs via FK relationships and safe uraian patterns (no bare
    __contains substring match) to prevent one piutang's nomor from accidentally
    matching another piutang whose nomor is a longer string starting with the same prefix.
    """
    if account is None:
        return Decimal('0')
    journal_ids = _piutang_journal_ids(piutang)
    if not journal_ids:
        return Decimal('0')
    result = (
        JurnalDetail.objects
        .filter(akun=account, jurnal_header_id__in=journal_ids)
        .aggregate(debit=Sum('debit'), kredit=Sum('kredit'))
    )
    return (result['debit'] or Decimal('0')) - (result['kredit'] or Decimal('0'))


def create_piutang_payment(piutang: PiutangHeader, data: dict, user=None) -> PiutangPenerimaan:
    jumlah = Decimal(str(data['jumlah_diterima']))
    with transaction.atomic():
        # Lock the piutang row for the duration of this transaction to prevent concurrent payment races
        piutang = PiutangHeader.objects.select_for_update().get(pk=piutang.pk)
        # For interest-bearing piutang, validate against total remaining schedule cash flows
        # (principal + remaining contractual interest), not just sisa_piutang which is principal-only.
        if piutang.jenis_bunga != 'tanpa_bunga' and piutang.jatuh_tempo:
            _schedule = compute_angsuran_schedule(piutang)
            sisa_tagihan = sum(r['sisa_bayar'] for r in _schedule) if _schedule else piutang.sisa_piutang
        else:
            sisa_tagihan = piutang.sisa_piutang
        if jumlah > sisa_tagihan:
            raise ValueError(
                f'Jumlah diterima ({jumlah:,.0f}) melebihi sisa tagihan ({sisa_tagihan:,.0f}).'
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
    tanggal = penerimaan.tanggal_terima
    jumlah = penerimaan.jumlah_diterima

    # ── PSAK 71: Pre-payment EIR accrual ────────────────────────────────────────
    # Recognise gross effective interest from last amortisation to payment date.
    # Dr. Piutang / Cr. Pendapatan Bunga Efektif (increases carrying amount).
    if (piutang.is_pv_adjusted
            and piutang.interest_income_account_id
            and piutang.pv_discount_rate):
        from_date = _pv_last_amortization_date(piutang)
        bunga_efektif = _pv_effective_interest_days(piutang, from_date, tanggal)
        if abs(bunga_efektif) >= Decimal('0.005'):
            ar_account_eir = (
                piutang.coa_piutang_lancar_account
                if piutang.coa_piutang_lancar_account_id
                else piutang.coa_piutang_account
            )
            amort_nomor = _next_piutang_journal_number('TRX-PIU-PV')
            amort_header = JurnalHeader.objects.create(
                tanggal=tanggal,
                nomor_transaksi=amort_nomor,
                uraian_transaksi=(
                    f'Amortisasi PV Piutang {piutang.nomor_piutang} — '
                    f'{from_date} s.d. {tanggal}'
                ),
                entitas_bisnis=piutang.entitas_bisnis,
                is_penyesuaian=False,
            )
            JurnalDetail.objects.bulk_create([
                JurnalDetail(
                    jurnal_header=amort_header,
                    akun=ar_account_eir,
                    debit=bunga_efektif,
                    kredit=Decimal('0'),
                ),
                JurnalDetail(
                    jurnal_header=amort_header,
                    akun=piutang.interest_income_account,
                    debit=Decimal('0'),
                    kredit=bunga_efektif,
                ),
            ])

    # ── Payment journal ──────────────────────────────────────────────────────────
    ar_account = (
        piutang.coa_piutang_lancar_account
        if piutang.coa_piutang_lancar_account_id
        else piutang.coa_piutang_account
    )
    nomor = _next_piutang_journal_number('TRX-PIU-P')
    header = JurnalHeader.objects.create(
        tanggal=tanggal,
        nomor_transaksi=nomor,
        uraian_transaksi=f'Penerimaan Piutang {piutang.nomor_piutang} — {piutang.entitas_display}',
        entitas_bisnis=piutang.entitas_bisnis,
        is_penyesuaian=False,
    )

    if piutang.is_pv_adjusted and piutang.pv_discount_rate:
        # PSAK 71: full cash flow reduces carrying amount.
        # Contractual interest was already in the carrying amount via EIR; no split needed.
        if piutang.coa_piutang_lancar_account_id:
            bal_lancar = max(
                Decimal('0'),
                _net_debit_balance_for_piutang(piutang.coa_piutang_lancar_account, piutang),
            )
            credit_lancar = min(jumlah, bal_lancar)
            credit_lt = jumlah - credit_lancar
            payment_lines = [
                JurnalDetail(jurnal_header=header, akun=penerimaan.payment_account,
                             debit=jumlah, kredit=Decimal('0')),
            ]
            if credit_lancar > 0:
                payment_lines.append(JurnalDetail(
                    jurnal_header=header, akun=piutang.coa_piutang_lancar_account,
                    debit=Decimal('0'), kredit=credit_lancar,
                ))
            if credit_lt > 0:
                payment_lines.append(JurnalDetail(
                    jurnal_header=header, akun=piutang.coa_piutang_account,
                    debit=Decimal('0'), kredit=credit_lt,
                ))
            JurnalDetail.objects.bulk_create(payment_lines)
        else:
            JurnalDetail.objects.bulk_create([
                JurnalDetail(jurnal_header=header, akun=penerimaan.payment_account,
                             debit=jumlah, kredit=Decimal('0')),
                JurnalDetail(jurnal_header=header, akun=ar_account,
                             debit=Decimal('0'), kredit=jumlah),
            ])
        return header

    # ── Non-PV-adjusted: existing logic ──────────────────────────────────────────
    # For interest-bearing piutang with angsuran_no: split payment bunga dulu, sisanya pokok
    if (piutang.jenis_bunga != 'tanpa_bunga'
            and penerimaan.angsuran_no
            and piutang.interest_income_account_id):
        schedule = compute_angsuran_schedule(piutang)
        installment = next((r for r in schedule if r['no'] == penerimaan.angsuran_no), None)
        if installment:
            bunga_kontrak = installment['bunga']
            if jumlah >= installment['angsuran']:
                pokok_paid = installment['pokok']
                bunga_paid = bunga_kontrak
            elif jumlah >= bunga_kontrak:
                bunga_paid = bunga_kontrak
                pokok_paid = jumlah - bunga_kontrak
            else:
                bunga_paid = jumlah
                pokok_paid = Decimal('0')
            entries = [
                JurnalDetail(jurnal_header=header, akun=penerimaan.payment_account,
                             debit=jumlah, kredit=Decimal('0')),
            ]
            if pokok_paid > 0:
                entries.append(JurnalDetail(
                    jurnal_header=header, akun=ar_account,
                    debit=Decimal('0'), kredit=pokok_paid,
                ))
            if bunga_paid > 0:
                entries.append(JurnalDetail(
                    jurnal_header=header, akun=piutang.interest_income_account,
                    debit=Decimal('0'), kredit=bunga_paid,
                ))
            JurnalDetail.objects.bulk_create(entries)
            return header

    # Default non-PV: Dr. Kas / Cr. Piutang (tanpa_bunga or no angsuran_no)
    if piutang.coa_piutang_lancar_account_id:
        bal_lancar = max(
            Decimal('0'),
            _net_debit_balance_for_piutang(piutang.coa_piutang_lancar_account, piutang),
        )
        credit_lancar = min(jumlah, bal_lancar)
        credit_lt = jumlah - credit_lancar
        payment_lines = [
            JurnalDetail(jurnal_header=header, akun=penerimaan.payment_account,
                         debit=jumlah, kredit=Decimal('0')),
        ]
        if credit_lancar > 0:
            payment_lines.append(JurnalDetail(
                jurnal_header=header, akun=piutang.coa_piutang_lancar_account,
                debit=Decimal('0'), kredit=credit_lancar,
            ))
        if credit_lt > 0:
            payment_lines.append(JurnalDetail(
                jurnal_header=header, akun=piutang.coa_piutang_account,
                debit=Decimal('0'), kredit=credit_lt,
            ))
        JurnalDetail.objects.bulk_create(payment_lines)
    else:
        JurnalDetail.objects.bulk_create([
            JurnalDetail(jurnal_header=header, akun=penerimaan.payment_account,
                         debit=jumlah, kredit=Decimal('0')),
            JurnalDetail(jurnal_header=header, akun=ar_account,
                         debit=Decimal('0'), kredit=jumlah),
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


def _compute_rkl_detail(piutang: PiutangHeader, as_of_date) -> Decimal:
    """
    PSAK 71: carrying amount of current-year installments.

    carrying_current = nominal_current − net_amort_current
    where net_amort_current = Σ(bunga_efektif) [net EIR] for current-window periods.

    Returns Decimal('0') if no current installments exist.
    """
    try:
        cutoff = as_of_date.replace(year=as_of_date.year + 1)
    except ValueError:
        cutoff = as_of_date.replace(year=as_of_date.year + 1, day=28)

    schedule = compute_angsuran_schedule(piutang)
    if schedule:
        all_unpaid = [r for r in schedule if r['status'] != 'lunas']
        current_rows = [
            r for r in all_unpaid
            if as_of_date < r['tanggal'] <= cutoff
        ]
        nominal_current = sum(
            max(
                Decimal('0'),
                row['pokok'] - max(Decimal('0'), row.get('paid', Decimal('0')) - row['bunga']),
            )
            for row in current_rows
        )
    else:
        nominal_current = (
            piutang.sisa_piutang
            if piutang.jatuh_tempo and as_of_date < piutang.jatuh_tempo <= cutoff
            else Decimal('0')
        )

    if nominal_current <= 0:
        return Decimal('0')

    if not piutang.is_pv_adjusted or not piutang.nilai_wajar_awal:
        return nominal_current

    if schedule:
        amort = compute_amortization_schedule_pv(piutang)
        if amort:
            amort_by_date = {r['tanggal']: r['bunga_efektif'] for r in amort}
            net_amort_current = sum(
                amort_by_date.get(row['tanggal'], Decimal('0'))
                for row in current_rows
            ).quantize(Decimal('0.0001'))
        else:
            net_amort_current = Decimal('0')
    else:
        i_daily = (1 + float(piutang.pv_discount_rate) / 100) ** (1 / 365) - 1
        pv_current = Decimal('0')
        if piutang.jatuh_tempo:
            days = (piutang.jatuh_tempo - as_of_date).days
            if days > 0:
                pv_current = piutang.sisa_piutang / Decimal(str((1 + i_daily) ** days))
        net_amort_current = (nominal_current - pv_current).quantize(Decimal('0.0001'))

    carrying_current = (nominal_current - net_amort_current).quantize(Decimal('0.0001'))
    return max(Decimal('0'), carrying_current)


def create_reklasifikasi_bagian_lancar(
    piutang: PiutangHeader,
    dari_akun,
    ke_akun,
    tanggal,
    user=None,
    dari_akun_deferred=None,
    ke_akun_deferred=None,
) -> PiutangReklasifikasi:
    """
    PSAK 71: reklasifikasi carrying amount (not nominal + deferred separately).
    dari_akun_deferred / ke_akun_deferred are accepted for signature compatibility but ignored.
    """
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

    carrying_current = _compute_rkl_detail(piutang, tanggal)
    if carrying_current <= 0:
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
            JurnalDetail(jurnal_header=jurnal, akun=dari_akun,
                         debit=Decimal('0'), kredit=carrying_current),
            JurnalDetail(jurnal_header=jurnal, akun=ke_akun,
                         debit=carrying_current, kredit=Decimal('0')),
        ])

        rkl = PiutangReklasifikasi.objects.create(
            piutang_header=piutang,
            tanggal=tanggal,
            dari_akun=dari_akun,
            ke_akun=ke_akun,
            jumlah=carrying_current,
            jumlah_deferred=None,
            dari_akun_deferred=None,
            ke_akun_deferred=None,
            keterangan=f'Bagian lancar {periode_tahun}-{periode_bulan:02d}',
            jurnal=jurnal,
            periode_bulan=periode_bulan,
            periode_tahun=periode_tahun,
            created_by=user,
        )
        _log(piutang, 'REKLASIFIKASI', user=user,
             after={'jumlah': str(carrying_current)})
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
        tanggal_terima = penerimaan.tanggal_terima
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

        # ── SAK ETAP: clean up associated amortisation journals ─────────────
        if piutang.is_pv_adjusted:
            nom = piutang.nomor_piutang

            # 1. Period amortisation (date-based): only remove if no other
            #    payment on the same date still holds ownership of this journal.
            other_same_date = (
                PiutangPenerimaan.objects
                .filter(piutang_header=piutang, tanggal_terima=tanggal_terima)
                .exclude(pk=penerimaan.pk)
                .exists()
            )
            if not other_same_date:
                period_amort = JurnalHeader.objects.filter(
                    uraian_transaksi__startswith=f'Amortisasi PV Piutang {nom} — ',
                    uraian_transaksi__endswith=f' s.d. {tanggal_terima}',
                    tanggal=tanggal_terima,
                ).first()
                if period_amort:
                    period_amort.details.all().delete()
                    period_amort.delete()


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


def _long_term_bagian_lancar_aging(piutang, as_of_date: date) -> list:
    """
    SAK ETAP: for long-term receivables, returns a list of (amount, due_date) tuples,
    one per unpaid installment due within 12 months of as_of_date. Each installment is
    bucketed by its OWN due date so overdue and current entries land in separate buckets.
    The non-current portion (>12 months) is excluded — assessed via PV impairment.
    """
    cutoff = as_of_date.replace(year=as_of_date.year + 1)
    schedule = compute_angsuran_schedule(piutang)

    if not schedule:
        if piutang.jatuh_tempo and piutang.jatuh_tempo <= cutoff:
            return [(piutang.sisa_piutang, piutang.jatuh_tempo)]
        return []

    return [
        (row['sisa_bayar'], row['tanggal'])
        for row in schedule
        if row['status'] != 'lunas' and row['sisa_bayar'] > 0 and row['tanggal'] <= cutoff
    ]


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
            # SAK ETAP: each installment within 12 months enters aging in its OWN bucket
            for amount, due_date in _long_term_bagian_lancar_aging(piutang, today):
                key = _classify_bucket(due_date, today)
                buckets[key].append({
                    'piutang': piutang,
                    'angsuran_no': None,
                    'tanggal_angsuran': due_date,
                    'jumlah': amount,
                    'hari_lewat': max(0, (today - due_date).days),
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
            # SAK ETAP: each installment within 12 months gets its own row, bucketed by its due date
            for amount, due_date in _long_term_bagian_lancar_aging(piutang, today):
                bucket_key = _classify_bucket(due_date, today)
                long_term_rows.append({
                    'nomor_piutang': piutang.nomor_piutang,
                    'debitur': piutang.entitas_display,
                    'tanggal': piutang.tanggal,
                    'jatuh_tempo_efektif': due_date,
                    'jumlah_piutang': amount,
                    'bucket_key': bucket_key,
                    'bucket_label': _AGING_BUCKET_LABELS[bucket_key],
                    'hari_lewat': max(0, (today - due_date).days),
                    'angsuran_no': None,
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
        # SAK ETAP: only bagian lancar (≤12 months) enters aging; each installment in its own bucket.
        for amount, due_date in _long_term_bagian_lancar_aging(piutang, today):
            key = _classify_bucket(due_date, today)
            bucket_amounts[key] += amount
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


def compute_batch_penyisihan(tanggal) -> dict:
    """
    Compute batch allowance grouped by (entitas_bisnis, allowance_account, expense_account).
    Each piutang must have penyisihan_allowance_account and penyisihan_expense_account set.
    Piutangs without accounts are returned separately as 'unconfigured'.

    Returns:
        groups:        list of per-group dicts with entitas_bisnis, allowance_account,
                       expense_account, target_saldo, saldo_existing, delta, breakdown,
                       and piutang_list.
        unconfigured:  list of PiutangHeader with missing account config.
        piutang_count: total piutangs processed (configured + unconfigured).
        total_target:  sum of target_saldo across groups.
        total_delta:   sum of delta across groups.
    """
    rates = _get_rate_config()
    today = tanggal

    qs = (
        PiutangHeader.objects
        .filter(status__in=('open', 'partial', 'overdue'), is_specifically_impaired=False)
        .select_related(
            'penyisihan_allowance_account', 'penyisihan_expense_account',
            'entitas_bisnis',
        )
        .prefetch_related('penerimaan')
    )

    # group_key → {entitas_bisnis, allowance_account, expense_account, bucket_amounts, piutang_list}
    groups: dict = {}
    unconfigured: list = []
    piutang_count = 0

    for piutang in qs:
        piutang_count += 1

        if not piutang.penyisihan_allowance_account_id or not piutang.penyisihan_expense_account_id:
            unconfigured.append(piutang)
            continue

        gk = (
            piutang.entitas_bisnis_id,
            piutang.penyisihan_allowance_account_id,
            piutang.penyisihan_expense_account_id,
        )
        if gk not in groups:
            groups[gk] = {
                'entitas_bisnis': piutang.entitas_bisnis,
                'allowance_account': piutang.penyisihan_allowance_account,
                'expense_account': piutang.penyisihan_expense_account,
                'bucket_amounts': {k: Decimal('0') for k in _AGING_BUCKET_KEYS},
                'piutang_list': [],
            }
        g = groups[gk]

        if piutang.jenis_jangka_waktu == 'long_term' and piutang.jatuh_tempo:
            row_total = Decimal('0')
            for amount, due_date in _long_term_bagian_lancar_aging(piutang, today):
                key = _classify_bucket(due_date, today)
                g['bucket_amounts'][key] += amount
                row_total += (amount * rates.get(key, Decimal('0')) / 100).quantize(Decimal('0.01'))
            g['piutang_list'].append({'piutang': piutang, 'penyisihan': row_total})
        else:
            key = _classify_bucket(piutang.jatuh_tempo, today)
            amount = piutang.sisa_piutang
            g['bucket_amounts'][key] += amount
            row_total = (amount * rates.get(key, Decimal('0')) / 100).quantize(Decimal('0.01'))
            g['piutang_list'].append({'piutang': piutang, 'penyisihan': row_total})

    from .models import PiutangPenyisihan as _PP
    result_groups = []
    total_target = Decimal('0')
    total_delta = Decimal('0')

    for gk, g in groups.items():
        target_saldo = Decimal('0')
        breakdown = []
        for key in _AGING_BUCKET_KEYS:
            amt = g['bucket_amounts'][key]
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

        eb_id = gk[0]
        saldo_existing = Decimal(str(
            _PP.objects
            .filter(
                jenis='batch',
                allowance_account=g['allowance_account'],
                entitas_bisnis_id=eb_id,
                tanggal__lte=tanggal,
            )
            .aggregate(s=Sum('jumlah'))['s'] or Decimal('0')
        )).quantize(Decimal('0.01'))
        delta = (target_saldo - saldo_existing).quantize(Decimal('0.01'))

        total_target += target_saldo
        total_delta += delta
        result_groups.append({
            'entitas_bisnis': g['entitas_bisnis'],
            'allowance_account': g['allowance_account'],
            'expense_account': g['expense_account'],
            'target_saldo': target_saldo,
            'saldo_existing': saldo_existing,
            'delta': delta,
            'breakdown': breakdown,
            'piutang_list': g['piutang_list'],
        })

    return {
        'groups': result_groups,
        'unconfigured': unconfigured,
        'piutang_count': piutang_count,
        'total_target': total_target,
        'total_delta': total_delta,
    }


def create_batch_penyisihan_journal(
    batch_data: dict,
    tanggal, catatan='', periode_label='', user=None,
):
    """
    Create one journal per (entitas_bisnis, allowance_account) group with non-zero delta.
    Each journal is attributed to the entitas_bisnis of the piutang group.
    Returns list of PiutangPenyisihan entries created.
    """
    from .models import PiutangPenyisihan
    active_groups = [g for g in batch_data['groups'] if g['delta'] != 0]
    if not active_groups:
        raise ValueError('Semua delta adalah 0, tidak perlu jurnal.')
    created = []
    with transaction.atomic():
        for g in active_groups:
            delta = g['delta']
            abs_delta = abs(delta)
            allowance_account = g['allowance_account']
            expense_account = g['expense_account']
            eb = g.get('entitas_bisnis')
            eb_id = eb.pk if eb else None
            # Uniqueness per (periode_label, entitas_bisnis, allowance_account)
            if periode_label and PiutangPenyisihan.objects.filter(
                jenis='batch',
                periode_label=periode_label,
                entitas_bisnis_id=eb_id,
                allowance_account=allowance_account,
            ).exists():
                eb_name = eb.nama if eb else 'tanpa EB'
                raise ValueError(
                    f'Jurnal penyisihan batch untuk periode {periode_label}, '
                    f'EB {eb_name}, akun {allowance_account.kode_akun} sudah ada.'
                )
            nomor = _next_penyisihan_journal_number('TRX-PIU-PSH-B')
            eb_label = f' [{eb.nama}]' if eb else ''
            header = JurnalHeader.objects.create(
                tanggal=tanggal,
                nomor_transaksi=nomor,
                uraian_transaksi=(
                    f'Penyisihan Piutang Batch — {tanggal}'
                    f'{eb_label} [{allowance_account.kode_akun}]'
                ),
                is_penyesuaian=True,
                entitas_bisnis=eb,
            )
            if delta > 0:
                JurnalDetail.objects.bulk_create([
                    JurnalDetail(jurnal_header=header, akun=expense_account,
                                 debit=abs_delta, kredit=Decimal('0')),
                    JurnalDetail(jurnal_header=header, akun=allowance_account,
                                 debit=Decimal('0'), kredit=abs_delta),
                ])
            else:
                JurnalDetail.objects.bulk_create([
                    JurnalDetail(jurnal_header=header, akun=allowance_account,
                                 debit=abs_delta, kredit=Decimal('0')),
                    JurnalDetail(jurnal_header=header, akun=expense_account,
                                 debit=Decimal('0'), kredit=abs_delta),
                ])
            entry = PiutangPenyisihan.objects.create(
                piutang_header=None,
                entitas_bisnis=eb,
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
            created.append(entry)
    return created


def reverse_batch_penyisihan_journal(entry, user=None):
    """
    Reverse a single PiutangPenyisihan batch entry and its associated JurnalHeader.
    Deletes the journal and the penyisihan entry inside a transaction.
    """
    from .models import PiutangPenyisihan
    from apps.jurnal.models import JurnalHeader as _JH
    with transaction.atomic():
        header = entry.jurnal_header
        entry.delete()
        if header:
            header.delete()


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


# ── PV Carrying-Value Helpers ────────────────────────────────────────────────


def _pv_carrying_value(piutang: PiutangHeader) -> Decimal:
    """
    PSAK 71: carrying amount = net debit balance of piutang accounts across all journals.
    Includes both coa_piutang_account (LT) and coa_piutang_lancar_account (current) so
    reklasifikasi transfers (which shift balance between the two) are transparent.
    """
    if not piutang.is_pv_adjusted or not piutang.nilai_wajar_awal:
        return piutang.sisa_piutang
    account_ids = [piutang.coa_piutang_account_id]
    if piutang.coa_piutang_lancar_account_id:
        account_ids.append(piutang.coa_piutang_lancar_account_id)
    journal_ids = _piutang_journal_ids(piutang)
    if not journal_ids:
        return piutang.nilai_wajar_awal
    result = (
        JurnalDetail.objects
        .filter(akun_id__in=account_ids, jurnal_header_id__in=journal_ids)
        .aggregate(debit=Sum('debit'), kredit=Sum('kredit'))
    )
    net = (result['debit'] or Decimal('0')) - (result['kredit'] or Decimal('0'))
    return max(Decimal('0'), net.quantize(Decimal('0.0001')))


def _pv_last_amortization_date(piutang: PiutangHeader) -> date:
    """
    Date through which effective interest has been recognised.
    Uses the latest Amortization or Accrual journal date (reversals do NOT reset this —
    the reversal un-recognises income but interest still ran until the accrual date).
    Falls back to piutang.tanggal (inception) if no journals exist yet.
    """
    nom = piutang.nomor_piutang
    from django.db.models import Q
    last = (
        JurnalHeader.objects
        .filter(
            Q(uraian_transaksi__startswith=f'Amortisasi PV Piutang {nom} —') |
            Q(uraian_transaksi__startswith=f'Akrual PV Piutang {nom} —')
        )
        .order_by('-tanggal', '-nomor_transaksi')
        .values_list('tanggal', flat=True)
        .first()
    )
    return last if last else piutang.tanggal


def _pv_effective_interest_days(piutang: PiutangHeader, from_date: date, to_date: date) -> Decimal:
    """
    Effective interest for actual days elapsed between from_date and to_date,
    using compound daily rate: i_daily = (1 + annual_rate)^(1/365) − 1.
    Computed on the CURRENT carrying value (pre-payment, so call before updating jumlah_terbayar).
    """
    days = (to_date - from_date).days
    if days <= 0 or not piutang.pv_discount_rate:
        return Decimal('0')
    carrying = _pv_carrying_value(piutang)
    if carrying <= 0:
        return Decimal('0')
    i_daily = (1 + float(piutang.pv_discount_rate) / 100) ** (1 / 365) - 1
    bunga = float(carrying) * i_daily * days
    return Decimal(str(round(bunga, 4)))


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
    # Compound rate per period: (1 + annual_rate)^(months/12) - 1  (SAK ETAP effective interest)
    r_per_period = (1 + float(market_rate) / 100) ** (periode_months / 12) - 1
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

    if piutang.is_pv_adjusted and piutang.nilai_wajar_awal:
        # PSAK 71 amortised cost: Dr. Piutang at fair value / Cr. Revenue at fair value.
        # No deferred income — the discount is implicit in the carrying amount.
        pv = piutang.nilai_wajar_awal
        JurnalDetail.objects.create(
            jurnal_header=header,
            akun=piutang.coa_piutang_account,
            debit=pv,
            kredit=Decimal('0'),
        )
        total_detail = sum(d.jumlah for d in details) or pv
        cumulative = Decimal('0')
        detail_entries = []
        for i, detail in enumerate(details):
            if i == len(details) - 1:
                kredit = pv - cumulative
            else:
                kredit = (detail.jumlah / total_detail * pv).quantize(Decimal('0.0001'))
            cumulative += kredit
            detail_entries.append(JurnalDetail(
                jurnal_header=header,
                akun=detail.revenue_account,
                debit=Decimal('0'),
                kredit=kredit,
            ))
        JurnalDetail.objects.bulk_create(detail_entries)
    else:
        # Standard method: Dr. Piutang (face) / Cr. Revenue (face)
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
        # SAK ETAP: compute PV at posting if deferred_income_account and pv_discount_rate are set
        update_fields = ['status', 'is_locked']
        if piutang.deferred_income_account_id and piutang.pv_discount_rate and not piutang.nilai_wajar_awal:
            piutang.nilai_wajar_awal = compute_present_value(piutang, piutang.pv_discount_rate)
            piutang.is_pv_adjusted = True
            update_fields += ['nilai_wajar_awal', 'is_pv_adjusted']
        jurnal = _create_piutang_ar_journal(piutang)
        piutang.status = 'open'
        piutang.is_locked = True
        piutang.save(update_fields=update_fields)
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
        update_fields = ['status', 'is_locked', 'approved_by', 'approved_at']
        if piutang.deferred_income_account_id and piutang.pv_discount_rate and not piutang.nilai_wajar_awal:
            piutang.nilai_wajar_awal = compute_present_value(piutang, piutang.pv_discount_rate)
            piutang.is_pv_adjusted = True
            update_fields += ['nilai_wajar_awal', 'is_pv_adjusted']
        jurnal = _create_piutang_ar_journal(piutang)
        piutang.status = 'open'
        piutang.is_locked = True
        piutang.approved_by = user
        piutang.approved_at = timezone.now()
        piutang.save(update_fields=update_fields)
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
    # Compound rate per period: (1 + annual_rate)^(months/12) - 1
    r_per_period = (1 + float(piutang.pv_discount_rate) / 100) ** (periode_months / 12) - 1
    carrying = float(piutang.nilai_wajar_awal)
    rows = []
    for row in schedule:
        bunga_efektif_gross = carrying * r_per_period
        bunga_kontrak = float(row.get('bunga') or 0)
        # Net discount amortization = effective − contractual coupon.
        # Can be negative when contractual coupon > effective interest
        # (e.g. late periods of a flat-rate loan where CA has declined below face).
        # Do NOT clamp — over-clamping causes cumulative over-recognition of discount.
        net_amortization = bunga_efektif_gross - bunga_kontrak
        cf = float(row['angsuran'])
        # Carrying evolves: add full effective, subtract full angsuran cash flow
        carrying = carrying + bunga_efektif_gross - cf
        rows.append({
            'periode': row['no'],
            'tanggal': row['tanggal'],
            'bunga_efektif': Decimal(str(round(net_amortization, 4))),
            'bunga_efektif_gross': Decimal(str(round(bunga_efektif_gross, 4))),
            'cash_flow': row['angsuran'],
            'carrying_value': Decimal(str(round(carrying, 4))),
        })
    return rows


def create_pv_adjustment_journal(
    piutang: PiutangHeader,
    interest_income_account,
    tanggal,
    catatan='',
    user=None,
    periode_no: int | None = None,
) -> JurnalHeader:
    """PSAK 71: Dr. Piutang (gross EIR) / Cr. Pendapatan Bunga Efektif."""
    if not piutang.is_pv_adjusted or not piutang.nilai_wajar_awal or not piutang.pv_discount_rate:
        raise ValueError('Piutang belum disesuaikan nilai wajar (PV).')
    amort = compute_amortization_schedule_pv(piutang)
    if not amort:
        raise ValueError('Jadwal amortisasi PV tidak tersedia.')

    if periode_no is None:
        prefix_pattern = f'Amortisasi PV Piutang {piutang.nomor_piutang}'
        recorded = JurnalHeader.objects.filter(
            uraian_transaksi__startswith=prefix_pattern,
        ).count()
        periode_no = recorded + 1

    if periode_no < 1 or periode_no > len(amort):
        raise ValueError(f'Periode {periode_no} tidak valid (total {len(amort)} periode).')

    row = amort[periode_no - 1]
    bunga = row['bunga_efektif_gross']
    if bunga <= Decimal('0.005'):
        raise ValueError('Bunga efektif nol, tidak perlu jurnal.')

    ar_account = (
        piutang.coa_piutang_lancar_account
        if piutang.coa_piutang_lancar_account_id
        else piutang.coa_piutang_account
    )
    with transaction.atomic():
        nomor = _next_piutang_journal_number('TRX-PIU-PV')
        header = JurnalHeader.objects.create(
            tanggal=tanggal,
            nomor_transaksi=nomor,
            uraian_transaksi=f'Amortisasi PV Piutang {piutang.nomor_piutang} — Periode {periode_no}',
            entitas_bisnis=piutang.entitas_bisnis,
            is_penyesuaian=True,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(
                jurnal_header=header,
                akun=ar_account,
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


def create_pv_accrual_journal(
    piutang: PiutangHeader,
    tanggal: date,
    interest_income_account=None,
    catatan: str = '',
    user=None,
) -> JurnalHeader:
    """
    PSAK 71: period-end accrual journal.
    Dr. Piutang (gross EIR for days elapsed) / Cr. Pendapatan Bunga Efektif.
    Must be paired with a reversal at start of next period.
    """
    if not piutang.is_pv_adjusted or not piutang.pv_discount_rate:
        raise ValueError('Piutang belum disesuaikan nilai wajar (PV).')
    income_account = interest_income_account or piutang.interest_income_account
    if not income_account:
        raise ValueError('Akun Pendapatan Bunga Efektif diperlukan.')

    from_date = _pv_last_amortization_date(piutang)
    bunga = _pv_effective_interest_days(piutang, from_date, tanggal)
    if bunga <= Decimal('0'):
        raise ValueError('Tidak ada selisih bunga efektif yang dapat diakrualkan untuk periode ini.')

    nom = piutang.nomor_piutang
    n_accrual = JurnalHeader.objects.filter(
        uraian_transaksi__startswith=f'Akrual PV Piutang {nom} —'
    ).count()
    n_reversal = JurnalHeader.objects.filter(
        uraian_transaksi__startswith=f'Balik Akrual PV Piutang {nom} —'
    ).count()
    if n_accrual > n_reversal:
        raise ValueError(
            'Masih ada jurnal akrual yang belum dibalik. Balik akrual sebelumnya terlebih dahulu.'
        )

    ar_account = (
        piutang.coa_piutang_lancar_account
        if piutang.coa_piutang_lancar_account_id
        else piutang.coa_piutang_account
    )
    with transaction.atomic():
        nomor = _next_piutang_journal_number('TRX-PIU-PV')
        header = JurnalHeader.objects.create(
            tanggal=tanggal,
            nomor_transaksi=nomor,
            uraian_transaksi=f'Akrual PV Piutang {nom} — s.d. {tanggal}',
            entitas_bisnis=piutang.entitas_bisnis,
            is_penyesuaian=True,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(
                jurnal_header=header,
                akun=ar_account,
                debit=bunga,
                kredit=Decimal('0'),
            ),
            JurnalDetail(
                jurnal_header=header,
                akun=income_account,
                debit=Decimal('0'),
                kredit=bunga,
            ),
        ])
        _log(piutang, 'EDITED', user=user,
             after={'pv_akrual': str(bunga), 'tanggal': str(tanggal)})
    return header


def create_pv_accrual_reversal(
    piutang: PiutangHeader,
    tanggal: date,
    catatan: str = '',
    user=None,
) -> JurnalHeader:
    """
    Reverse the last un-reversed period-end accrual journal.
    Swaps debit/credit of the original accrual entry.
    """
    nom = piutang.nomor_piutang
    last_accrual = (
        JurnalHeader.objects
        .filter(uraian_transaksi__startswith=f'Akrual PV Piutang {nom} —')
        .order_by('-tanggal', '-nomor_transaksi')
        .prefetch_related('details')
        .first()
    )
    if not last_accrual:
        raise ValueError('Tidak ada jurnal akrual PV yang dapat dibalik.')

    n_reversal = JurnalHeader.objects.filter(
        uraian_transaksi__startswith=f'Balik Akrual PV Piutang {nom} —'
    ).count()
    n_accrual = JurnalHeader.objects.filter(
        uraian_transaksi__startswith=f'Akrual PV Piutang {nom} —'
    ).count()
    if n_reversal >= n_accrual:
        raise ValueError('Semua jurnal akrual PV sudah dibalik.')

    with transaction.atomic():
        nomor = _next_piutang_journal_number('TRX-PIU-PV')
        reversal = JurnalHeader.objects.create(
            tanggal=tanggal,
            nomor_transaksi=nomor,
            uraian_transaksi=f'Balik Akrual PV Piutang {nom} — {last_accrual.nomor_transaksi}',
            entitas_bisnis=piutang.entitas_bisnis,
            is_penyesuaian=True,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(
                jurnal_header=reversal,
                akun=d.akun,
                debit=d.kredit,    # swap
                kredit=d.debit,
            )
            for d in last_accrual.details.all()
        ])
        _log(piutang, 'EDITED', user=user,
             after={'pv_balik_akrual': last_accrual.nomor_transaksi, 'tanggal': str(tanggal)})
    return reversal
