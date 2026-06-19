from __future__ import annotations
from datetime import date
from decimal import Decimal

from django.db.models import Q

from .exceptions import TarifPajakTidakDitemukan, MasaPajakTerkunciError, PajakStatusError
from .models import TarifPajak, BracketPPhOP, MasaPajak, PajakTransaksi


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
