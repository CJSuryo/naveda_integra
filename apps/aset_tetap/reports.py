"""Laporan aset tetap — depreciation schedule (proyeksi) & agregasi per dimensi."""
from copy import copy
from decimal import Decimal

from .models import AsetTetapRecord
from .services import calculate_depreciation


def depreciation_schedule(aset, periods: int = 12, days_per_period: int = 30):
    """Proyeksi penyusutan ke depan (on-the-fly, tanpa menyimpan).

    Mengembalikan list dict per periode: index, penyusutan, akumulasi_akhir, nilai_buku_akhir.
    Berhenti bila nilai buku mencapai residu.
    """
    rows = []
    # kerja di atas salinan agar tidak mengubah record asli
    proxy = copy(aset)
    residu = aset.nilai_residu
    for i in range(1, periods + 1):
        amount = calculate_depreciation(proxy, tahun_ke=((i - 1) // 12) + 1, days=days_per_period)
        nilai_buku = proxy.total_value - proxy.akumulasi_penyusutan
        susutkan = min(amount, nilai_buku - residu)
        if susutkan < 0:
            susutkan = Decimal('0')
        proxy.akumulasi_penyusutan += susutkan
        rows.append({
            'index': i,
            'penyusutan': susutkan,
            'akumulasi_akhir': proxy.akumulasi_penyusutan,
            'nilai_buku_akhir': proxy.total_value - proxy.akumulasi_penyusutan,
        })
        if proxy.total_value - proxy.akumulasi_penyusutan <= residu:
            break
    return rows


def laporan_penyusutan(entitas_bisnis=None, kategori=None, lokasi=None, departemen=None):
    """Agregasi ringkas nilai aset per aset dengan filter dimensi.

    Mengembalikan list dict: aset_number, nama, kategori, lokasi, departemen,
    perolehan, akumulasi, nilai_buku.
    """
    qs = AsetTetapRecord.objects.select_related('item', 'item__kategori', 'lokasi_aset', 'departemen')
    if entitas_bisnis:
        qs = qs.filter(entitas_bisnis=entitas_bisnis)
    if kategori:
        qs = qs.filter(item__kategori=kategori)
    if lokasi:
        qs = qs.filter(lokasi_aset=lokasi)
    if departemen:
        qs = qs.filter(departemen=departemen)
    rows = []
    for a in qs:
        rows.append({
            'aset_number': a.aset_number,
            'nama': a.item.nama if a.item else '',
            'kategori': a.item.kategori.nama if a.item and a.item.kategori else '',
            'lokasi': a.lokasi_aset.nama if a.lokasi_aset else '',
            'departemen': a.departemen.nama if a.departemen else '',
            'perolehan': a.total_value,
            'akumulasi': a.akumulasi_penyusutan,
            'nilai_buku': a.nilai_buku,
        })
    return rows
