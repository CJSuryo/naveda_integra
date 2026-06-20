from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.jurnal.models import JurnalDetail, JurnalHeader
from apps.pajak.models import PajakTransaksi
from apps.pajak.services import sync_pajak, confirm_pajak as confirm_pajak_trx, batal_pajak as batal_pajak_trx

from .models import (
    AsetKontrak, EntriPengakuan, JadwalPengakuan,
    KewajibabPelaksanaan, KPTaxLine, PendapatanEntitasBisnis, PendapatanEventLog, PendapatanHeader, PendapatanItem,
)


TAX_TYPE_MAP = {
    'ppn_keluaran': 'ppn_umum',
    'pph_23': 'pph_23_jasa',
    'pph_21': 'pph_21_bukan_pegawai',
    'pph_4_2': 'pph_4_2_sewa',
}

SIFAT_PAJAK_MAP = {
    'ppn_keluaran': 'potong_pungut',  # seller collects PPN → liability (Dr Kas, Cr Utang PPN)
    'pph_23': 'prepaid',              # buyer withholds → prepaid tax asset (Dr PPh DDM, Cr Kas)
    'pph_21': 'prepaid',              # buyer withholds → prepaid tax asset (Dr PPh DDM, Cr Kas)
    'pph_4_2': 'prepaid',             # buyer withholds final tax → Dr akun_pajak, Cr akun_lawan
}


# ── PSAK 72 Step 4: Price Allocation ─────────────────────────────────────────

def compute_alokasi_harga(header: PendapatanHeader) -> dict[int, Decimal]:
    """
    PSAK 72 Step 4: allocate total transaction price across KPs proportionally
    by nilai_kontrak (standalone selling price proxy).
    Returns {kp_id: alokasi_harga}. Last KP absorbs any rounding remainder.
    """
    from decimal import ROUND_HALF_UP

    kps = list(
        KewajibabPelaksanaan.objects.filter(pendapatan_eb__pendapatan_header=header)
    )
    if not kps:
        return {}

    total_ssp = sum(kp.nilai_kontrak for kp in kps)
    if total_ssp == 0:
        return {kp.id: Decimal('0') for kp in kps}

    # Transaction price = sum of SSPs (no bundle discount model yet)
    transaction_price = total_ssp

    alokasi = {}
    total_allocated = Decimal('0')

    for i, kp in enumerate(kps):
        if i == len(kps) - 1:
            # Last item absorbs rounding remainder
            alokasi[kp.id] = transaction_price - total_allocated
        else:
            raw = kp.nilai_kontrak / total_ssp * transaction_price
            amount = raw.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
            alokasi[kp.id] = amount
            total_allocated += amount

    return alokasi


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

def compute_next_date(current_date: date, frekuensi: str) -> date:
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
    if not template.is_active:
        raise ValueError(f'Template "{template.nama}" tidak aktif.')
    with transaction.atomic():
        template = type(template).objects.select_for_update().get(pk=template.pk)
        if not template.is_active:
            raise ValueError(f'Template "{template.nama}" tidak aktif.')
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
            payment_account=template.payment_account,
        )

        PendapatanItem.objects.create(
            pendapatan_eb=eb_group,
            deskripsi_item=template.deskripsi_item,
            kategori=template.kategori,
            sub_transaction_type=template.sub_transaction_type,
            jumlah_bruto=template.jumlah,
            revenue_account=template.revenue_account,
            payment_account=template.payment_account,
        )

        new_next = compute_next_date(template.tanggal_berikutnya, template.frekuensi)
        template.tanggal_berikutnya = new_next
        if template.tanggal_selesai and new_next >= template.tanggal_selesai:
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

        for item in items:
            kp = PendapatanItem.objects.create(
                pendapatan_eb=eb_group,
                deskripsi_item=item['deskripsi_item'],
                kategori=item['kategori'],
                sub_transaction_type=item['sub_transaction_type'],
                nilai_kontrak=item.get('nilai_kontrak') or item.get('jumlah_bruto'),
                revenue_account=item['revenue_account'],
                payment_account=item.get('payment_account'),
                recognition_type=item.get('recognition_type', 'point_in_time'),
                ot_tipe_aliran=item.get('ot_tipe_aliran', ''),
                ot_progress_method=item.get('ot_progress_method', ''),
                ot_tanggal_mulai=item.get('ot_tanggal_mulai'),
                ot_tanggal_selesai=item.get('ot_tanggal_selesai'),
                ot_liabilitas_kontrak_acct=item.get('ot_liabilitas_kontrak_acct'),
                ot_aset_kontrak_acct=item.get('ot_aset_kontrak_acct'),
                ot_biaya_estimasi_total=item.get('ot_biaya_estimasi_total'),
            )
            for tl in item.get('tax_lines', []):
                KPTaxLine.objects.create(
                    kp=kp,
                    tax_type=tl['tax_type'],
                    tax=tl.get('tax'),
                    is_manual=tl.get('is_manual', False),
                    tax_account=tl['tax_account'],
                    tax_payment_account=tl['tax_payment_account'],
                )

        _log_event(header, 'CREATED', actor=user)

    return header


# ── Confirm ───────────────────────────────────────────────────────────────────

def _sync_confirm_tax_line(kp, header, tax_line, amount, entitas_bisnis=None, user=None):
    """Create and immediately confirm a PajakTransaksi for one KPTaxLine."""
    jenis_pajak = TAX_TYPE_MAP.get(tax_line.tax_type)
    if not jenis_pajak:
        return
    sifat_pajak = SIFAT_PAJAK_MAP.get(tax_line.tax_type, 'potong_pungut')
    # Hanya perlakukan sebagai override bila user benar-benar mengisi manual.
    # Bila auto (is_manual=False), biarkan sync_pajak menghitung ulang dari tarif
    # sehingga PajakTransaksi tidak terlabel override.
    override_amount = tax_line.tax if tax_line.is_manual else None
    pajak_trx = sync_pajak(
        source_type='pendapatan_kp',
        source_obj=kp,
        dpp=amount,
        tanggal=header.tanggal,
        jenis_pajak=jenis_pajak,
        akun_pajak=tax_line.tax_account,
        akun_lawan=tax_line.tax_payment_account,
        sifat_pajak=sifat_pajak,
        override_amount=override_amount,
        entitas_bisnis_override=entitas_bisnis,
    )
    confirm_pajak_trx(pajak_trx)


def _cancel_kp_pajak(kp):
    """
    Cancel all non-cancelled PajakTransaksi linked to a KP.
    Each batal_pajak call is independently atomic (internal to apps.pajak).
    """
    qs = PajakTransaksi.objects.filter(
        source_type='pendapatan_kp',
        source_id=kp.pk,
    ).exclude(status='dibatalkan')
    for pajak_trx in qs:
        batal_pajak_trx(pajak_trx)


def confirm_pendapatan(header: PendapatanHeader, user=None) -> None:
    """
    PSAK 72 confirm: process each KP through one of five recognition cases.

    Case 1: point_in_time + cash      → journal (payment_account / revenue_account)
    Case 2: point_in_time + credit    → journal + piutang
    Case 3: over_time + advance_payment_cash → journal (payment_account / liabilitas) + jadwal
    Case 4: over_time + periodic_billing     → jadwal only (no immediate journal)
    Case 5: over_time + performance_first    → journal (aset_kontrak / revenue) + AsetKontrak + jadwal
    """
    if header.status != 'draft':
        raise ValueError(
            f'Pendapatan {header.transaction_id} tidak dapat dikonfirmasi '
            f'karena status-nya adalah "{header.status}" (bukan "draft").'
        )

    with transaction.atomic():
        # Step 1: compute and persist price allocation for all KPs
        alokasi = compute_alokasi_harga(header)
        all_kps = list(
            KewajibabPelaksanaan.objects.filter(pendapatan_eb__pendapatan_header=header)
        )
        for kp in all_kps:
            if kp.id in alokasi:
                kp.harga_j = alokasi[kp.id]
                kp.save(update_fields=['harga_j'])

        # Step 2: per-group per-KP processing
        has_credit_pit = False
        for eb_group in header.entitas_groups.select_related('entitas_bisnis').prefetch_related(
            'items__revenue_account', 'items__payment_account',
            'items__tax_lines__tax_account', 'items__tax_lines__tax_payment_account',
            'items__ot_liabilitas_kontrak_acct', 'items__ot_aset_kontrak_acct',
        ).all():
            for kp in eb_group.items.all():
                harga_j = kp.harga_j
                pay_acct = kp.payment_account or eb_group.payment_account

                if kp.recognition_type == KewajibabPelaksanaan.RecognitionType.POINT_IN_TIME:
                    # Case 1 & 2: immediate recognition — books DPP only
                    _create_kp_journal(
                        header, eb_group, kp,
                        debit_acct=pay_acct,
                        credit_acct=kp.revenue_account,
                        amount=harga_j,
                        user=user,
                    )
                    for tax_line in kp.tax_lines.all():
                        _sync_confirm_tax_line(kp, header, tax_line, harga_j, entitas_bisnis=eb_group.entitas_bisnis, user=user)
                    if header.payment_type == 'credit':
                        has_credit_pit = True

                elif kp.recognition_type == KewajibabPelaksanaan.RecognitionType.OVER_TIME:
                    tipe = kp.ot_tipe_aliran

                    if tipe == 'advance_payment_cash':
                        # Case 3: cash received upfront → debit cash, credit liabilitas kontrak (DPP only)
                        if pay_acct is None:
                            raise ValueError(
                                f'KP "{kp.deskripsi_item}" tidak memiliki akun pembayaran untuk '
                                f'advance_payment_cash. Isi akun pembayaran sebelum mengkonfirmasi.'
                            )
                        _create_kp_journal(
                            header, eb_group, kp,
                            debit_acct=pay_acct,
                            credit_acct=kp.ot_liabilitas_kontrak_acct,
                            amount=harga_j,
                            user=user,
                        )
                        for tax_line in kp.tax_lines.all():
                            _sync_confirm_tax_line(kp, header, tax_line, harga_j, entitas_bisnis=eb_group.entitas_bisnis, user=user)
                        _create_jadwal(kp, harga_j, user)
                        _log_event(header, 'JADWAL_CREATED',
                                   description=f'KP {kp.pk} — advance_payment_cash', actor=user)

                    elif tipe == 'periodic_billing':
                        # Case 4: no immediate journal; jadwal drives future billing + per-period tax
                        _create_jadwal(kp, harga_j, user)
                        _log_event(header, 'JADWAL_CREATED',
                                   description=f'KP {kp.pk} — periodic_billing', actor=user)

                    elif tipe == 'performance_first':
                        # Case 5: service delivered before cash → aset kontrak / revenue (DPP only)
                        _create_kp_journal(
                            header, eb_group, kp,
                            debit_acct=kp.ot_aset_kontrak_acct,
                            credit_acct=kp.revenue_account,
                            amount=harga_j,
                            user=user,
                        )
                        for tax_line in kp.tax_lines.all():
                            _sync_confirm_tax_line(kp, header, tax_line, harga_j, entitas_bisnis=eb_group.entitas_bisnis, user=user)
                        # Record contract asset
                        AsetKontrak.objects.create(
                            kp=kp,
                            tanggal=header.tanggal,
                            nilai=harga_j,
                            nilai_tersisa=harga_j,
                        )
                        _create_jadwal(kp, harga_j, user)
                        _log_event(header, 'JADWAL_CREATED',
                                   description=f'KP {kp.pk} — performance_first', actor=user)
                        _log_event(header, 'JOURNAL_PSAK72',
                                   description=f'KP {kp.pk} — aset kontrak created', actor=user)

        # Case 2: create exactly one piutang for all point_in_time credit KPs
        if has_credit_pit:
            from apps.piutang.services import create_piutang_from_pendapatan
            piutang = create_piutang_from_pendapatan(header, user)
            _log_event(header, 'PIUTANG_CREATED', description=piutang.nomor_piutang, actor=user)

        header.status = 'confirmed'
        header.save(update_fields=['status'])
        _log_event(header, 'CONFIRMED', actor=user)


# ── PSAK 72 Confirm Helpers ───────────────────────────────────────────────────

def _create_kp_journal(header, eb_group, kp, debit_acct, credit_acct, amount, user=None):
    """
    Create main journal for one KP recognition event. Books DPP only.
    Tax is handled separately by apps.pajak.services.
    """
    if debit_acct is None:
        raise ValueError(
            f'KP "{kp.deskripsi_item}" tidak memiliki akun debit untuk pembuatan jurnal.'
        )
    if credit_acct is None:
        raise ValueError(
            f'KP "{kp.deskripsi_item}" tidak memiliki akun kredit untuk pembuatan jurnal.'
        )

    nomor = _next_journal_number('TRX-PND-J')
    jh = JurnalHeader.objects.create(
        tanggal=header.tanggal,
        nomor_transaksi=nomor,
        uraian_transaksi=(
            f'Pendapatan {header.transaction_id} — {eb_group.entitas_bisnis.nama} — KP {kp.pk}'
        ),
        entitas_bisnis=eb_group.entitas_bisnis,
        is_penyesuaian=False,
    )
    JurnalDetail.objects.bulk_create([
        JurnalDetail(jurnal_header=jh, akun=debit_acct,  debit=amount,       kredit=Decimal('0')),
        JurnalDetail(jurnal_header=jh, akun=credit_acct, debit=Decimal('0'), kredit=amount),
    ])
    _log_event(header, 'JOURNAL_CREATED', description=jh.nomor_transaksi, actor=user)
    return jh


def _create_jadwal(kp: KewajibabPelaksanaan, harga_j: Decimal, user=None) -> JadwalPengakuan:
    """
    Create a JadwalPengakuan + EntriPengakuan entries from the KP's ot_* staging fields.
    Straight-line: generates one EntriPengakuan per calendar month.
    """
    jadwal = JadwalPengakuan.objects.create(
        kp=kp,
        tipe_aliran=kp.ot_tipe_aliran,
        progress_method=kp.ot_progress_method,
        tanggal_mulai=kp.ot_tanggal_mulai,
        tanggal_selesai=kp.ot_tanggal_selesai,
        liabilitas_kontrak_acct=kp.ot_liabilitas_kontrak_acct,
        aset_kontrak_acct=kp.ot_aset_kontrak_acct,
        biaya_estimasi_total=kp.ot_biaya_estimasi_total,
        nilai_total=harga_j,
        nilai_diakui=Decimal('0'),
    )

    if kp.ot_progress_method == JadwalPengakuan.ProgressMethod.STRAIGHT_LINE:
        start = jadwal.tanggal_mulai.replace(day=1)
        end = jadwal.tanggal_selesai
        months = (end.year - start.year) * 12 + end.month - start.month + 1
        months = max(months, 1)
        monthly = (harga_j / months).quantize(Decimal('0.0001'))
        remainder = harga_j - monthly * months
        current = start
        entri_list = []
        for i in range(months):
            entri_list.append(EntriPengakuan(
                jadwal=jadwal,
                tanggal_target=current,
                nilai=monthly + (remainder if i == months - 1 else Decimal('0')),
            ))
            current = (current + relativedelta(months=1)).replace(day=1)
        EntriPengakuan.objects.bulk_create(entri_list)

    return jadwal


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

        # Cancel linked PajakTransaksi for every KP under this header
        for kp in KewajibabPelaksanaan.objects.filter(pendapatan_eb__pendapatan_header=header):
            _cancel_kp_pajak(kp)

        # Cancel linked piutang
        from apps.piutang.models import PiutangHeader
        linked_piutang = PiutangHeader.objects.filter(
            source_pendapatan=header,
            status__in=('open', 'draft'),
        )
        linked_piutang.update(status='cancelled')

        # Void all new PSAK 72 records
        JadwalPengakuan.objects.filter(
            kp__pendapatan_eb__pendapatan_header=header
        ).update(status=JadwalPengakuan.Status.VOIDED)

        EntriPengakuan.objects.filter(
            jadwal__kp__pendapatan_eb__pendapatan_header=header,
            status=EntriPengakuan.Status.PENDING,
        ).update(status=EntriPengakuan.Status.SKIPPED)

        AsetKontrak.objects.filter(
            kp__pendapatan_eb__pendapatan_header=header,
            status=AsetKontrak.Status.ACTIVE,
        ).update(status=AsetKontrak.Status.VOIDED)

        header.status = 'voided'
        header.save(update_fields=['status'])
        _log_event(header, 'VOIDED', actor=user)


# ── PSAK 72 Recognition: recognize_entry ─────────────────────────────────────

def recognize_entry(entry_id: int, user, journal_date=None) -> None:
    """
    Recognize revenue for one EntriPengakuan.

    Journal entries depend on jadwal.tipe_aliran:
    - advance_payment_cash: Debit liabilitas_kontrak_acct, Credit kp.revenue_account
    - periodic_billing: Debit payment_account, Credit kp.revenue_account
    - performance_first: No journal (revenue booked at confirm). Mark recognized only.

    After journaling:
    - entri.status = 'recognized', entri.nilai_diakui = entri.nilai
    - entri.jurnal_header = jurnal (or None for performance_first)
    - jadwal.nilai_diakui += entri.nilai
    - If jadwal.nilai_diakui >= jadwal.nilai_total: jadwal.status = 'completed'
    - Log 'RECOGNIZE' event on the header
    """
    entri = EntriPengakuan.objects.select_related(
        'jadwal__kp__pendapatan_eb__pendapatan_header',
        'jadwal__kp__pendapatan_eb__payment_account',
        'jadwal__kp__revenue_account',
        'jadwal__kp__payment_account',
        'jadwal__liabilitas_kontrak_acct',
    ).prefetch_related('jadwal__kp__tax_lines__tax_account').get(pk=entry_id)

    jadwal = entri.jadwal
    kp = jadwal.kp
    eb_group = kp.pendapatan_eb
    header = eb_group.pendapatan_header
    tipe_aliran = jadwal.tipe_aliran
    amount = entri.nilai
    jh = None

    with transaction.atomic():
        if tipe_aliran == 'advance_payment_cash':
            # Debit liabilitas kontrak, Credit revenue (tax already settled at confirm)
            debit_acct = jadwal.liabilitas_kontrak_acct or kp.ot_liabilitas_kontrak_acct
            jh = _create_recognition_journal(
                header=header, eb_group=eb_group, kp=kp,
                debit_acct=debit_acct, credit_acct=kp.revenue_account,
                amount=amount, journal_date=journal_date, user=user,
            )

        elif tipe_aliran == 'periodic_billing':
            # Debit payment account, Credit revenue + prorate tax per period
            pay_acct = kp.payment_account or eb_group.payment_account
            tax_lines_data = _prorate_tax_lines(kp, amount, jadwal.nilai_total)
            jh = _create_recognition_journal(
                header=header, eb_group=eb_group, kp=kp,
                debit_acct=pay_acct, credit_acct=kp.revenue_account,
                amount=amount, journal_date=journal_date, user=user,
                tax_lines_data=tax_lines_data,
            )

        # performance_first: no new journal needed (revenue booked at confirm)

        # Update entri
        entri.status = EntriPengakuan.Status.RECOGNIZED
        entri.nilai_diakui = amount
        entri.jurnal_header = jh
        entri.save(update_fields=['status', 'nilai_diakui', 'jurnal_header'])

        # Update jadwal
        jadwal.nilai_diakui = jadwal.nilai_diakui + amount
        if jadwal.nilai_diakui >= jadwal.nilai_total:
            jadwal.status = JadwalPengakuan.Status.COMPLETED
        jadwal.save(update_fields=['nilai_diakui', 'status'])

        _log_event(header, 'RECOGNIZE',
                   description=f'Entri {entri.pk} — {tipe_aliran} — {amount}',
                   actor=user)


def _prorate_tax_lines(kp, amount: Decimal, nilai_total: Decimal) -> list:
    """Return [{'akun': Akun, 'amount': Decimal}, ...] for KPTaxLines with manual override amounts, prorated."""
    if nilai_total <= 0:
        return []
    result = []
    for tl in kp.tax_lines.select_related('tax_account').all():
        if tl.tax and tl.tax > 0:
            prorated = (tl.tax * amount / nilai_total).quantize(Decimal('0.0001'))
            result.append({'akun': tl.tax_account, 'amount': prorated})
    return result


def _create_recognition_journal(
    header, eb_group, kp, debit_acct, credit_acct, amount,
    journal_date=None, user=None, tax_lines_data=None,
):
    """
    Create recognition journal for EntriPengakuan.
    tax_lines_data: list of {'akun': Akun, 'amount': Decimal}.
    """
    if debit_acct is None:
        raise ValueError(
            f'KP "{kp.deskripsi_item}" tidak memiliki akun debit untuk pengakuan pendapatan.'
        )
    if credit_acct is None:
        raise ValueError(
            f'KP "{kp.deskripsi_item}" tidak memiliki akun kredit untuk pengakuan pendapatan.'
        )
    from django.utils import timezone as tz
    tanggal = journal_date or tz.now().date()
    tax_lines_data = tax_lines_data or []
    total_tax = sum(tl['amount'] for tl in tax_lines_data)
    debit_total = amount + total_tax
    nomor = _next_journal_number('TRX-PND-RE')
    jh = JurnalHeader.objects.create(
        tanggal=tanggal,
        nomor_transaksi=nomor,
        uraian_transaksi=(
            f'Pengakuan Pendapatan {header.transaction_id} — {eb_group.entitas_bisnis.nama} — KP {kp.pk}'
        ),
        entitas_bisnis=eb_group.entitas_bisnis,
        is_penyesuaian=False,
    )
    details = [
        JurnalDetail(jurnal_header=jh, akun=debit_acct, debit=debit_total, kredit=Decimal('0')),
        JurnalDetail(jurnal_header=jh, akun=credit_acct, debit=Decimal('0'), kredit=amount),
    ]
    for tl in tax_lines_data:
        details.append(
            JurnalDetail(jurnal_header=jh, akun=tl['akun'], debit=Decimal('0'), kredit=tl['amount'])
        )
    JurnalDetail.objects.bulk_create(details)
    _log_event(header, 'JOURNAL_CREATED', description=jh.nomor_transaksi, actor=user)
    return jh


def recognize_percentage_completion(jadwal_id: int, progress_pct: Decimal, user, journal_date=None) -> EntriPengakuan:
    """
    Recognize revenue for a percentage_completion jadwal.

    progress_pct is the NEW CUMULATIVE completion percentage (0 < pct <= 100).
    Incremental amount = (pct/100 * nilai_total) - nilai_diakui.
    Creates an EntriPengakuan and appropriate journal, then updates the jadwal.
    """
    jadwal = JadwalPengakuan.objects.select_related(
        'kp__pendapatan_eb__pendapatan_header',
        'kp__pendapatan_eb__entitas_bisnis',
        'kp__pendapatan_eb__payment_account',
        'kp__revenue_account',
        'kp__payment_account',
        'liabilitas_kontrak_acct',
    ).prefetch_related('kp__tax_lines__tax_account').get(pk=jadwal_id)

    if jadwal.progress_method != JadwalPengakuan.ProgressMethod.PERCENTAGE_COMPLETION:
        raise ValueError('Jadwal ini bukan metode Persentase Selesai.')
    if jadwal.status != JadwalPengakuan.Status.ACTIVE:
        raise ValueError(f'Jadwal sudah {jadwal.get_status_display()}, tidak dapat diakui lagi.')

    kp = jadwal.kp
    eb_group = kp.pendapatan_eb
    header = eb_group.pendapatan_header

    progress_pct = Decimal(str(progress_pct))
    if not (Decimal('0') < progress_pct <= Decimal('100')):
        raise ValueError('Progress harus antara 0 (eksklusif) dan 100 persen.')

    cumulative = (progress_pct / Decimal('100') * jadwal.nilai_total).quantize(Decimal('0.0001'))
    amount = cumulative - jadwal.nilai_diakui
    if amount <= Decimal('0'):
        raise ValueError(
            f'Progress {progress_pct}% tidak menghasilkan nilai pengakuan tambahan. '
            f'Sudah diakui: {jadwal.nilai_diakui} dari {jadwal.nilai_total}.'
        )
    amount = min(amount, jadwal.nilai_belum_diakui)

    from django.utils import timezone as tz
    tanggal = journal_date or tz.now().date()

    with transaction.atomic():
        jh = None
        tipe = jadwal.tipe_aliran

        if tipe == 'advance_payment_cash':
            # Tax already settled at confirm → no tax here
            debit_acct = jadwal.liabilitas_kontrak_acct or kp.ot_liabilitas_kontrak_acct
            jh = _create_recognition_journal(
                header, eb_group, kp, debit_acct, kp.revenue_account,
                amount, tanggal, user,
            )
        elif tipe == 'periodic_billing':
            # Prorate tax per partial recognition
            pay_acct = kp.payment_account or eb_group.payment_account
            tax_lines_data = _prorate_tax_lines(kp, amount, jadwal.nilai_total)
            jh = _create_recognition_journal(
                header, eb_group, kp, pay_acct, kp.revenue_account,
                amount, tanggal, user, tax_lines_data=tax_lines_data,
            )
        # performance_first: revenue already booked at confirm; no journal at recognition

        entri = EntriPengakuan.objects.create(
            jadwal=jadwal,
            tanggal_target=tanggal,
            nilai=amount,
            nilai_diakui=amount,
            status=EntriPengakuan.Status.RECOGNIZED,
            jurnal_header=jh,
        )

        jadwal.nilai_diakui += amount
        if jadwal.nilai_diakui >= jadwal.nilai_total:
            jadwal.status = JadwalPengakuan.Status.COMPLETED
        jadwal.save(update_fields=['nilai_diakui', 'status'])

        _log_event(
            header, 'RECOGNIZE',
            description=f'Persentase Selesai {progress_pct}% — Rp {amount} — Jadwal {jadwal.pk}',
            actor=user,
        )

        return entri


# ── PSAK 72: konversi_aset_kontrak_ke_piutang ─────────────────────────────────

def konversi_aset_kontrak_ke_piutang(aset_id: int, user) -> None:
    """
    Convert an active AsetKontrak to piutang.

    Steps:
    1. Assert aset.status == 'active'
    2. Create swap journal: Debit payment_account, Credit ot_aset_kontrak_acct
    3. Update aset.status = 'converted', aset.nilai_tersisa = 0, aset.jurnal_header = jurnal
    4. Log 'ASSET_CONVERTED' event on the header
    """
    aset = AsetKontrak.objects.select_related(
        'kp__pendapatan_eb__pendapatan_header',
        'kp__pendapatan_eb__payment_account',
        'kp__pendapatan_eb__entitas_bisnis',
        'kp__payment_account',
        'kp__ot_aset_kontrak_acct',
        'kp__revenue_account',
    ).get(pk=aset_id)

    if aset.status != AsetKontrak.Status.ACTIVE:
        raise ValueError(
            f'AsetKontrak {aset.pk} tidak dapat dikonversi karena statusnya '
            f'adalah "{aset.status}" (bukan "active").'
        )

    kp = aset.kp
    eb_group = kp.pendapatan_eb
    header = eb_group.pendapatan_header

    pay_acct = kp.payment_account or eb_group.payment_account
    aset_acct = kp.ot_aset_kontrak_acct
    nilai_konversi = aset.nilai_tersisa

    with transaction.atomic():
        # Swap journal: Dr payment/piutang, Cr aset kontrak
        if pay_acct is None:
            raise ValueError(
                f'KP "{kp.deskripsi_item}" tidak memiliki akun pembayaran untuk konversi aset kontrak.'
            )
        if aset_acct is None:
            raise ValueError(
                f'KP "{kp.deskripsi_item}" tidak memiliki akun aset kontrak untuk konversi.'
            )

        nomor = _next_journal_number('TRX-PND-AK')
        from django.utils import timezone as tz
        today = tz.now().date()
        jh = JurnalHeader.objects.create(
            tanggal=today,
            nomor_transaksi=nomor,
            uraian_transaksi=(
                f'Konversi Aset Kontrak ke Piutang {header.transaction_id} — KP {kp.pk}'
            ),
            entitas_bisnis=eb_group.entitas_bisnis,
            is_penyesuaian=False,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(jurnal_header=jh, akun=pay_acct, debit=nilai_konversi, kredit=Decimal('0')),
            JurnalDetail(jurnal_header=jh, akun=aset_acct, debit=Decimal('0'), kredit=nilai_konversi),
        ])
        _log_event(header, 'JOURNAL_CREATED', description=jh.nomor_transaksi, actor=user)

        # Create piutang for the converted amount
        from apps.piutang.models import PiutangHeader as _PH, PiutangDetail as _PD, PiutangAuditLog as _PAL
        piutang = _PH.objects.create(
            tanggal=today,
            entitas_bisnis=eb_group.entitas_bisnis,
            debitur=str(eb_group.entitas_bisnis),
            deskripsi=(
                f'Piutang dari Konversi Aset Kontrak {header.transaction_id} — KP {kp.pk}'
            ),
            source_type='from_pendapatan',
            source_pendapatan=header,
            jumlah_pokok=nilai_konversi,
            status='open',
            coa_piutang_account=pay_acct,
            created_by=user,
        )
        _PD.objects.create(
            piutang_header=piutang,
            deskripsi=kp.deskripsi_item[:255],
            jumlah=nilai_konversi,
            revenue_account=kp.revenue_account,
        )
        _PAL.objects.create(
            piutang_header=piutang,
            nomor_piutang=piutang.nomor_piutang,
            action='CREATED',
            user=user,
            before_json={},
            after_json={'status': 'open', 'jumlah_pokok': str(nilai_konversi)},
        )

        # Update aset — link to piutang and zero out
        aset.status = AsetKontrak.Status.CONVERTED
        aset.nilai_tersisa = Decimal('0')
        aset.jurnal_header = jh
        aset.piutang = piutang
        aset.save(update_fields=['status', 'nilai_tersisa', 'jurnal_header', 'piutang'])

        _log_event(header, 'ASSET_CONVERTED',
                   description=f'AsetKontrak {aset.pk} → {piutang.nomor_piutang}',
                   actor=user)
        _log_event(header, 'PIUTANG_CREATED_KP',
                   description=f'{piutang.nomor_piutang} dari KP {kp.pk}',
                   actor=user)


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
            if pay_acct is None:
                raise ValueError(
                    f'Item "{item.deskripsi_item}" tidak memiliki akun pembayaran. '
                    f'Isi akun pembayaran pada item atau grup entitas bisnis sebelum mengkonfirmasi.'
                )
            cr_acct = item.revenue_account
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
            for tl in item.tax_lines.select_related('tax_account').all():
                if tl.tax and tl.tax > 0:
                    entries.append(JurnalDetail(
                        jurnal_header=jh, akun=tl.tax_account,
                        debit=Decimal('0'), kredit=tl.tax,
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
        .aggregate(s=Sum('nilai_kontrak'))['s'] or Decimal('0')
    )
    cash_bulan_ini = (
        PendapatanItem.objects
        .filter(
            pendapatan_eb__pendapatan_header__in=this_month_qs,
            pendapatan_eb__pendapatan_header__payment_type='cash',
        )
        .aggregate(s=Sum('nilai_kontrak'))['s'] or Decimal('0')
    )
    credit_bulan_ini = (
        PendapatanItem.objects
        .filter(
            pendapatan_eb__pendapatan_header__in=this_month_qs,
            pendapatan_eb__pendapatan_header__payment_type='credit',
        )
        .aggregate(s=Sum('nilai_kontrak'))['s'] or Decimal('0')
    )

    # Last month
    last_month_qs = confirmed_qs.filter(tanggal__gte=last_month_start, tanggal__lt=last_month_end)
    total_bulan_lalu = (
        PendapatanItem.objects
        .filter(pendapatan_eb__pendapatan_header__in=last_month_qs)
        .aggregate(s=Sum('nilai_kontrak'))['s'] or Decimal('0')
    )

    return {
        'total_bulan_ini': total_bulan_ini,
        'total_bulan_lalu': total_bulan_lalu,
        'cash_bulan_ini': cash_bulan_ini,
        'credit_bulan_ini': credit_bulan_ini,
    }
