"""Laporan aset tetap — depreciation schedule (proyeksi) & agregasi per dimensi."""
from collections import defaultdict
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


def asset_register(eb_lv1_ids, *, kategori_id=None, lokasi_id=None,
                   departemen_id=None, pic=None, status=None, group_by='kategori'):
    """Asset register terfilter dengan subtotal per dimensi grouping.

    group_by: 'kategori' | 'lokasi' | 'departemen'. Nilai perolehan memakai
    total_value (quantity*harga_perolehan). Kembalikan rows + subtotals + grand.
    """
    qs = (AsetTetapRecord.objects
          .filter(entitas_bisnis_id__in=list(eb_lv1_ids))
          .select_related('item', 'item__kategori', 'lokasi_aset', 'departemen'))
    if kategori_id:
        qs = qs.filter(item__kategori_id=kategori_id)
    if lokasi_id:
        qs = qs.filter(lokasi_aset_id=lokasi_id)
    if departemen_id:
        qs = qs.filter(departemen_id=departemen_id)
    if pic:
        qs = qs.filter(pic__icontains=pic)
    if status:
        qs = qs.filter(status=status)

    def _group_key(a):
        if group_by == 'lokasi':
            return a.lokasi_aset.nama if a.lokasi_aset else '(Tanpa Lokasi)'
        if group_by == 'departemen':
            return a.departemen.nama if a.departemen else '(Tanpa Departemen)'
        return a.item.kategori.nama if a.item and a.item.kategori else '(Tanpa Kategori)'

    rows = []
    subtotals = defaultdict(lambda: {
        'harga_perolehan': Decimal('0'), 'akumulasi': Decimal('0'),
        'nilai_buku': Decimal('0')})
    grand = {'harga_perolehan': Decimal('0'), 'akumulasi': Decimal('0'),
             'nilai_buku': Decimal('0')}
    for a in qs:
        perolehan = a.total_value or Decimal('0')
        akum = a.akumulasi_penyusutan or Decimal('0')
        nb = a.nilai_buku
        gk = _group_key(a)
        rows.append({
            'aset': a,
            'kode': a.aset_number,
            'nama': a.item.nama if a.item else '',
            'kategori': a.item.kategori.nama if a.item and a.item.kategori else '',
            'lokasi': a.lokasi_aset.nama if a.lokasi_aset else '',
            'departemen': a.departemen.nama if a.departemen else '',
            'pic': a.pic or '',
            'tanggal_perolehan': a.tanggal_perolehan,
            'harga_perolehan': perolehan,
            'akumulasi_penyusutan': akum,
            'nilai_buku': nb,
            'status': a.get_status_display(),
            'kondisi': a.get_kondisi_display(),
            'group_key': gk,
        })
        subtotals[gk]['harga_perolehan'] += perolehan
        subtotals[gk]['akumulasi'] += akum
        subtotals[gk]['nilai_buku'] += nb
        grand['harga_perolehan'] += perolehan
        grand['akumulasi'] += akum
        grand['nilai_buku'] += nb

    rows.sort(key=lambda r: (r['group_key'], r['kode']))
    return {'rows': rows, 'subtotals': dict(subtotals), 'grand_total': grand,
            'group_by': group_by}
