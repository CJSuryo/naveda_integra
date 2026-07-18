from __future__ import annotations
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q

from .exceptions import TarifPajakTidakDitemukan, MasaPajakTerkunciError, PajakStatusError
from .models import TarifPajak, BracketPPhOP, MasaPajak, PajakTransaksi
from apps.jurnal.models import JurnalHeader, JurnalDetail


def resolve_pajak_sources(trx_list: list[PajakTransaksi]) -> list[PajakTransaksi]:
    """Attach source_label/source_url to each PajakTransaksi for display.

    Resolves 'pendapatan_kp' and 'sales_item' source types back to their
    parent transaction (PendapatanHeader / SalesHeader) with a link to its
    detail page. Other source types fall back to a plain type+id label.
    """
    from django.urls import reverse

    kp_ids = [pt.source_id for pt in trx_list if pt.source_type == 'pendapatan_kp']
    kp_to_header = {}
    if kp_ids:
        from apps.pendapatan.models import KewajibabPelaksanaan
        for kp in KewajibabPelaksanaan.objects.filter(pk__in=kp_ids).select_related(
            'pendapatan_eb__pendapatan_header'
        ):
            kp_to_header[kp.pk] = kp.pendapatan_eb.pendapatan_header

    si_ids = [pt.source_id for pt in trx_list if pt.source_type == 'sales_item']
    si_to_header = {}
    if si_ids:
        from apps.sales.models import SalesItem
        for si in SalesItem.objects.filter(pk__in=si_ids).select_related(
            'sales_eb__sales_header'
        ):
            si_to_header[si.pk] = si.sales_eb.sales_header

    for pt in trx_list:
        if pt.source_type == 'pendapatan_kp' and pt.source_id in kp_to_header:
            h = kp_to_header[pt.source_id]
            pt.source_label = h.transaction_id
            pt.source_url = reverse('pendapatan:detail', args=[h.pk])
        elif pt.source_type == 'sales_item' and pt.source_id in si_to_header:
            h = si_to_header[pt.source_id]
            pt.source_label = h.transaction_id
            pt.source_url = reverse('sales:detail', args=[h.pk])
        else:
            pt.source_label = f'{pt.get_source_type_display()} #{pt.source_id}'
            pt.source_url = None
    return trx_list


def tarif_efektif(jumlah_pajak: Decimal, dpp: Decimal) -> Decimal:
    """
    Effective rate against full DPP, for display on overridden records.
    Returns jumlah_pajak / dpp x 100 (4dp), or 0 if dpp is missing/zero.
    """
    if not dpp or dpp <= 0:
        return Decimal('0')
    return (jumlah_pajak / dpp * Decimal('100')).quantize(Decimal('0.0001'))


def get_tarif_record(jenis_pajak: str, tanggal: date) -> TarifPajak:
    """Return the active TarifPajak record for jenis_pajak on tanggal."""
    qs = (
        TarifPajak.objects
        .filter(jenis_pajak=jenis_pajak, berlaku_mulai__lte=tanggal)
        .filter(Q(berlaku_sampai__gte=tanggal) | Q(berlaku_sampai__isnull=True))
    )
    try:
        return qs.latest('berlaku_mulai')
    except TarifPajak.DoesNotExist:
        raise TarifPajakTidakDitemukan(
            f'Tidak ada tarif aktif untuk {jenis_pajak} pada {tanggal}.'
        )


def hitung_progresif(pkp: Decimal, tanggal: date) -> Decimal:
    """Apply progressive Pasal 17 brackets to pkp. Returns total tax."""
    brackets = BracketPPhOP.objects.filter(berlaku_mulai__lte=tanggal).order_by('berlaku_mulai', 'batas_bawah')
    latest_mulai = brackets.values_list('berlaku_mulai', flat=True).order_by('-berlaku_mulai').first()
    if not latest_mulai:
        return Decimal('0')
    brackets = brackets.filter(berlaku_mulai=latest_mulai)

    total = Decimal('0')
    remaining = pkp
    for bracket in brackets:
        if remaining <= 0:
            break
        lower = bracket.batas_bawah
        upper = bracket.batas_atas
        layer_width = (upper - lower + 1) if upper is not None else remaining
        taxable = min(remaining, layer_width)
        total += taxable * bracket.tarif_persen / Decimal('100')
        remaining -= taxable
    return total


def compute_pajak(jenis_pajak: str, dpp: Decimal, tanggal: date) -> dict:
    """
    Compute tax for jenis_pajak on dpp at tanggal.

    Returns dict with keys: dpp_efektif, tarif_persen, jumlah_pajak.
    pph_21_bukan_pegawai uses hitung_progresif; all others use faktor_dpp x tarif_persen.
    """
    if jenis_pajak == 'pph_21_bukan_pegawai':
        pkp = dpp * Decimal('0.50')
        jumlah = hitung_progresif(pkp, tanggal)
        tarif_record = get_tarif_record(jenis_pajak, tanggal)
        return {
            'dpp_efektif': pkp,
            'tarif_persen': tarif_record.tarif_persen,
            'jumlah_pajak': jumlah,
        }

    tarif_record = get_tarif_record(jenis_pajak, tanggal)
    dpp_efektif = dpp * tarif_record.faktor_dpp
    jumlah = dpp_efektif * tarif_record.tarif_persen / Decimal('100')

    return {
        'dpp_efektif': dpp_efektif,
        'tarif_persen': tarif_record.tarif_persen,
        'jumlah_pajak': jumlah,
    }


def sync_pajak(
    source_type: str,
    source_obj,
    dpp: Decimal,
    tanggal: date,
    jenis_pajak: str,
    akun_pajak,
    akun_lawan,
    sifat_pajak: str,
    override_amount: Decimal | None = None,
    entitas_bisnis_override=None,
) -> PajakTransaksi:
    """
    Create a draft PajakTransaksi for source_obj.

    Priority for jumlah_pajak:
      1. override_amount (if provided and > 0) → is_overridden=True
      2. source_obj.tax (if attribute exists and > 0) → is_overridden=True
      3. compute_pajak from TarifPajak → is_overridden=False
    Raises MasaPajakTerkunciError if the target period is locked.
    """
    masa_date = tanggal.replace(day=1)
    masa, _ = MasaPajak.objects.get_or_create(
        tahun=masa_date.year, bulan=masa_date.month,
        defaults={'status': 'open'},
    )
    if masa.status == 'locked':
        raise MasaPajakTerkunciError(
            f'Masa pajak {masa_date:%Y-%m} sudah terkunci. '
            'Buka kunci terlebih dahulu sebelum memposting transaksi baru.'
        )

    effective_override = (
        override_amount if (override_amount is not None and override_amount > 0)
        else getattr(source_obj, 'tax', None)
    )
    if effective_override and effective_override > 0:
        jumlah_pajak = effective_override
        tarif_persen = tarif_efektif(jumlah_pajak, dpp)
        is_overridden = True
    else:
        hasil = compute_pajak(jenis_pajak, dpp, tanggal)
        jumlah_pajak = hasil['jumlah_pajak']
        tarif_persen = hasil['tarif_persen']
        is_overridden = False

    return PajakTransaksi.objects.create(
        source_type=source_type,
        source_id=source_obj.pk,
        masa_pajak=masa_date,
        jenis_pajak=jenis_pajak,
        dpp=dpp,
        tarif_persen=tarif_persen,
        jumlah_pajak=jumlah_pajak,
        sifat_pajak=sifat_pajak,
        status='draft',
        is_overridden=is_overridden,
        akun_pajak=akun_pajak,
        akun_lawan=akun_lawan,
        entitas_bisnis=entitas_bisnis_override if entitas_bisnis_override is not None else getattr(source_obj, 'entitas_bisnis', None),
    )


def _next_pajak_journal_number() -> str:
    """Generate next sequential TRX-PAJ-XXXXXXXX number."""
    prefix = 'TRX-PAJ'
    last = (
        JurnalHeader.objects
        .filter(nomor_transaksi__startswith=prefix)
        .order_by('-nomor_transaksi')
        .values_list('nomor_transaksi', flat=True)
        .first()
    )
    if last:
        try:
            seq = int(last.split('-')[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f'{prefix}-{seq:08d}'


def post_jurnal_pajak(pajak_trx: PajakTransaksi, reverse: bool = False) -> JurnalHeader:
    """Create JurnalHeader + 2 JurnalDetail. Rounds jumlah_pajak to 2dp ROUND_HALF_UP.

    reverse=True membalik arah debit/kredit — dipakai untuk nota retur/kredit yang
    membalik pajak transaksi asal (mis. retur pelanggan mengurangi PPN Keluaran).
    """
    jumlah = pajak_trx.jumlah_pajak.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    if pajak_trx.sifat_pajak == 'potong_pungut':
        akun_debit  = pajak_trx.akun_lawan
        akun_kredit = pajak_trx.akun_pajak
    else:  # prepaid
        akun_debit  = pajak_trx.akun_pajak
        akun_kredit = pajak_trx.akun_lawan

    if reverse:
        akun_debit, akun_kredit = akun_kredit, akun_debit

    nomor = _next_pajak_journal_number()
    jh = JurnalHeader.objects.create(
        tanggal=pajak_trx.masa_pajak,
        nomor_transaksi=nomor,
        uraian_transaksi=(
            f'{"Retur Pajak" if reverse else "Jurnal Pajak"} — {pajak_trx.get_jenis_pajak_display()} '
            f'— {pajak_trx.source_type}:{pajak_trx.source_id}'
        ),
        entitas_bisnis=pajak_trx.entitas_bisnis,
        is_penyesuaian=False,
    )
    JurnalDetail.objects.bulk_create([
        JurnalDetail(jurnal_header=jh, akun=akun_debit,  debit=jumlah,      kredit=Decimal('0')),
        JurnalDetail(jurnal_header=jh, akun=akun_kredit, debit=Decimal('0'), kredit=jumlah),
    ])
    return jh


def confirm_pajak(pajak_trx: PajakTransaksi, reverse: bool = False) -> JurnalHeader:
    """Validate draft status + unlocked period, set status=final, post journal.

    reverse=True membalik arah jurnal (nota retur/kredit)."""
    if pajak_trx.status != 'draft':
        raise PajakStatusError(
            f'PajakTransaksi {pajak_trx.pk} berstatus "{pajak_trx.status}", bukan "draft".'
        )
    masa_date = pajak_trx.masa_pajak
    try:
        masa = MasaPajak.objects.get(tahun=masa_date.year, bulan=masa_date.month)
        if masa.status == 'locked':
            raise MasaPajakTerkunciError(
                f'Masa pajak {masa_date:%Y-%m} sudah terkunci.'
            )
    except MasaPajak.DoesNotExist:
        pass  # period not created yet means open

    jh = post_jurnal_pajak(pajak_trx, reverse=reverse)
    pajak_trx.jurnal_header = jh
    pajak_trx.status = 'final'
    pajak_trx.save(update_fields=['jurnal_header', 'status'])
    return jh


def batal_pajak(pajak_trx: PajakTransaksi) -> None:
    """Cancel pajak_trx. If a journal exists, post a reversal (swap debit/kredit)."""
    from django.db import transaction
    with transaction.atomic():
        if pajak_trx.jurnal_header_id:
            original_jh = pajak_trx.jurnal_header
            nomor = _next_pajak_journal_number()
            rev_jh = JurnalHeader.objects.create(
                tanggal=original_jh.tanggal,
                nomor_transaksi=nomor,
                uraian_transaksi=f'Reversal Pajak — {original_jh.nomor_transaksi}',
                entitas_bisnis=original_jh.entitas_bisnis,
                is_penyesuaian=True,
            )
            JurnalDetail.objects.bulk_create([
                JurnalDetail(
                    jurnal_header=rev_jh,
                    akun=d.akun,
                    debit=d.kredit,
                    kredit=d.debit,
                )
                for d in original_jh.details.all()
            ])
        pajak_trx.jurnal_header = None
        pajak_trx.status = 'dibatalkan'
        pajak_trx.save(update_fields=['jurnal_header', 'status'])


def override_pajak(pajak_trx: PajakTransaksi, jumlah_baru: Decimal, modified_by=None) -> PajakTransaksi:
    """
    Manual override: reverse existing journal, set new amount, post new journal.
    Works on both draft and final records.
    """
    from django.utils import timezone
    batal_pajak(pajak_trx)
    pajak_trx.jumlah_pajak = jumlah_baru
    pajak_trx.tarif_persen = tarif_efektif(jumlah_baru, pajak_trx.dpp)
    pajak_trx.is_overridden = True
    pajak_trx.modified_by = modified_by
    pajak_trx.modified_at = timezone.now()
    pajak_trx.status = 'draft'
    pajak_trx.jurnal_header = None
    pajak_trx.save(update_fields=[
        'jumlah_pajak', 'tarif_persen', 'is_overridden', 'modified_by', 'modified_at', 'status', 'jurnal_header'
    ])
    jh = post_jurnal_pajak(pajak_trx)
    pajak_trx.jurnal_header = jh
    pajak_trx.status = 'final'
    pajak_trx.save(update_fields=['jurnal_header', 'status'])
    return pajak_trx
