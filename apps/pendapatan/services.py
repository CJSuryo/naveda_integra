from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.jurnal.models import JurnalDetail, JurnalHeader

from .models import (
    AsetKontrak, EntriPengakuan, JadwalPengakuan,
    KewajibabPelaksanaan, PendapatanEntitasBisnis, PendapatanEventLog, PendapatanHeader, PendapatanItem,
)


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

        PendapatanItem.objects.bulk_create([
            PendapatanItem(
                pendapatan_eb=eb_group,
                deskripsi_item=item['deskripsi_item'],
                kategori=item['kategori'],
                sub_transaction_type=item['sub_transaction_type'],
                nilai_kontrak=item.get('nilai_kontrak') or item.get('jumlah_bruto'),
                revenue_account=item['revenue_account'],
                payment_account=item.get('payment_account'),
                tax=item.get('tax'),
                tax_type=item.get('tax_type', ''),
                tax_account=item.get('tax_account'),
                tax_payment=item.get('tax_payment', ''),
                tax_payment_account=item.get('tax_payment_account'),
                recognition_type=item.get('recognition_type', 'point_in_time'),
                ot_tipe_aliran=item.get('ot_tipe_aliran', ''),
                ot_progress_method=item.get('ot_progress_method', ''),
                ot_tanggal_mulai=item.get('ot_tanggal_mulai'),
                ot_tanggal_selesai=item.get('ot_tanggal_selesai'),
                ot_liabilitas_kontrak_acct=item.get('ot_liabilitas_kontrak_acct'),
                ot_aset_kontrak_acct=item.get('ot_aset_kontrak_acct'),
                ot_biaya_estimasi_total=item.get('ot_biaya_estimasi_total'),
            )
            for item in items
        ])

        _log_event(header, 'CREATED', actor=user)

    return header


# ── Confirm ───────────────────────────────────────────────────────────────────

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
        for eb_group in header.entitas_groups.prefetch_related(
            'items__revenue_account', 'items__payment_account',
            'items__ot_liabilitas_kontrak_acct', 'items__ot_aset_kontrak_acct',
        ).all():
            for kp in eb_group.items.all():
                harga_j = kp.harga_j
                pay_acct = kp.payment_account or eb_group.payment_account

                if kp.recognition_type == KewajibabPelaksanaan.RecognitionType.POINT_IN_TIME:
                    # Case 1 & 2: immediate recognition
                    _create_kp_journal(
                        header, eb_group, kp,
                        debit_acct=pay_acct,
                        credit_acct=kp.revenue_account,
                        amount=harga_j,
                        user=user,
                    )
                    if header.payment_type == 'credit':
                        # Case 2: also create piutang
                        from apps.piutang.services import create_piutang_from_pendapatan
                        piutang = create_piutang_from_pendapatan(header, user)
                        _log_event(header, 'PIUTANG_CREATED', description=piutang.nomor_piutang, actor=user)

                elif kp.recognition_type == KewajibabPelaksanaan.RecognitionType.OVER_TIME:
                    tipe = kp.ot_tipe_aliran

                    if tipe == 'advance_payment_cash':
                        # Case 3: cash received upfront → debit cash, credit liabilitas kontrak
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
                        _create_jadwal(kp, harga_j, user)
                        _log_event(header, 'JADWAL_CREATED',
                                   description=f'KP {kp.pk} — advance_payment_cash', actor=user)

                    elif tipe == 'periodic_billing':
                        # Case 4: no immediate journal; jadwal drives future billing
                        _create_jadwal(kp, harga_j, user)
                        _log_event(header, 'JADWAL_CREATED',
                                   description=f'KP {kp.pk} — periodic_billing', actor=user)

                    elif tipe == 'performance_first':
                        # Case 5: service delivered before cash → debit aset kontrak, credit revenue
                        _create_kp_journal(
                            header, eb_group, kp,
                            debit_acct=kp.ot_aset_kontrak_acct,
                            credit_acct=kp.revenue_account,
                            amount=harga_j,
                            user=user,
                        )
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

        header.status = 'confirmed'
        header.save(update_fields=['status'])
        _log_event(header, 'CONFIRMED', actor=user)


# ── PSAK 72 Confirm Helpers ───────────────────────────────────────────────────

def _create_kp_journal(header, eb_group, kp, debit_acct, credit_acct, amount, user=None):
    """Create a single two-line journal for one KP recognition event."""
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
        JurnalDetail(jurnal_header=jh, akun=debit_acct, debit=amount, kredit=Decimal('0')),
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
    ).get(pk=entry_id)

    jadwal = entri.jadwal
    kp = jadwal.kp
    eb_group = kp.pendapatan_eb
    header = eb_group.pendapatan_header
    tipe_aliran = jadwal.tipe_aliran
    amount = entri.nilai
    jh = None

    with transaction.atomic():
        if tipe_aliran == 'advance_payment_cash':
            # Debit liabilitas kontrak, Credit revenue
            debit_acct = jadwal.liabilitas_kontrak_acct or kp.ot_liabilitas_kontrak_acct
            credit_acct = kp.revenue_account
            jh = _create_recognition_journal(
                header=header,
                eb_group=eb_group,
                kp=kp,
                debit_acct=debit_acct,
                credit_acct=credit_acct,
                amount=amount,
                journal_date=journal_date,
                user=user,
            )

        elif tipe_aliran == 'periodic_billing':
            # Debit payment account (receivable), Credit revenue
            pay_acct = kp.payment_account or eb_group.payment_account
            credit_acct = kp.revenue_account
            jh = _create_recognition_journal(
                header=header,
                eb_group=eb_group,
                kp=kp,
                debit_acct=pay_acct,
                credit_acct=credit_acct,
                amount=amount,
                journal_date=journal_date,
                user=user,
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


def _create_recognition_journal(header, eb_group, kp, debit_acct, credit_acct, amount, journal_date=None, user=None):
    """Create a two-line recognition journal for EntriPengakuan."""
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
    JurnalDetail.objects.bulk_create([
        JurnalDetail(jurnal_header=jh, akun=debit_acct, debit=amount, kredit=Decimal('0')),
        JurnalDetail(jurnal_header=jh, akun=credit_acct, debit=Decimal('0'), kredit=amount),
    ])
    _log_event(header, 'JOURNAL_CREATED', description=jh.nomor_transaksi, actor=user)
    return jh


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
        jh = JurnalHeader.objects.create(
            tanggal=tz.now().date(),
            nomor_transaksi=nomor,
            uraian_transaksi=(
                f'Konversi Aset Kontrak ke Piutang {header.transaction_id} — KP {kp.pk}'
            ),
            entitas_bisnis=eb_group.entitas_bisnis,
            is_penyesuaian=False,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(jurnal_header=jh, akun=pay_acct, debit=aset.nilai_tersisa, kredit=Decimal('0')),
            JurnalDetail(jurnal_header=jh, akun=aset_acct, debit=Decimal('0'), kredit=aset.nilai_tersisa),
        ])
        _log_event(header, 'JOURNAL_CREATED', description=jh.nomor_transaksi, actor=user)

        # Update aset
        aset.status = AsetKontrak.Status.CONVERTED
        aset.nilai_tersisa = Decimal('0')
        aset.jurnal_header = jh
        aset.save(update_fields=['status', 'nilai_tersisa', 'jurnal_header'])

        _log_event(header, 'ASSET_CONVERTED',
                   description=f'AsetKontrak {aset.pk} dikonversi ke piutang',
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
