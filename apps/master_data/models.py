"""Master data models: Aset, Kewajiban, Ekuitas, TipeTransaksi, Akun, Bukti."""
from django.db import models


# ── Aset ─────────────────────────────────────────────────────────────────────

class AsetLv1(models.Model):
    kode = models.CharField(max_length=50, unique=True)
    nama = models.CharField(max_length=255)

    class Meta:
        verbose_name = 'Aset Level 1'
        verbose_name_plural = 'Aset Level 1'

    def __str__(self) -> str:
        return f'{self.kode} - {self.nama}'


class AsetLv2(models.Model):
    aset = models.ForeignKey(AsetLv1, on_delete=models.CASCADE, related_name='children', null=True, blank=True)
    kode = models.CharField(max_length=50, unique=True)
    nama = models.CharField(max_length=255)

    class Meta:
        verbose_name = 'Aset Level 2'
        verbose_name_plural = 'Aset Level 2'

    def __str__(self) -> str:
        return f'{self.kode} - {self.nama}'


# ── Kewajiban ─────────────────────────────────────────────────────────────────

class KewajibanLv1(models.Model):
    kode = models.CharField(max_length=50, unique=True)
    nama = models.CharField(max_length=255)

    class Meta:
        verbose_name = 'Kewajiban Level 1'
        verbose_name_plural = 'Kewajiban Level 1'

    def __str__(self) -> str:
        return f'{self.kode} - {self.nama}'


class KewajibanLv2(models.Model):
    kewajiban = models.ForeignKey(KewajibanLv1, on_delete=models.CASCADE, related_name='children', null=True, blank=True)
    kode = models.CharField(max_length=50, unique=True)
    nama = models.CharField(max_length=255)

    class Meta:
        verbose_name = 'Kewajiban Level 2'
        verbose_name_plural = 'Kewajiban Level 2'

    def __str__(self) -> str:
        return f'{self.kode} - {self.nama}'


# ── Ekuitas ───────────────────────────────────────────────────────────────────

class EkuitasLv1(models.Model):
    kode = models.CharField(max_length=50, unique=True)
    nama = models.CharField(max_length=255)

    class Meta:
        verbose_name = 'Ekuitas Level 1'
        verbose_name_plural = 'Ekuitas Level 1'

    def __str__(self) -> str:
        return f'{self.kode} - {self.nama}'


class EkuitasLv2(models.Model):
    ekuitas = models.ForeignKey(EkuitasLv1, on_delete=models.CASCADE, related_name='children', null=True, blank=True)
    kode = models.CharField(max_length=50, unique=True)
    nama = models.CharField(max_length=255)

    class Meta:
        verbose_name = 'Ekuitas Level 2'
        verbose_name_plural = 'Ekuitas Level 2'

    def __str__(self) -> str:
        return f'{self.kode} - {self.nama}'


# ── Akun ──────────────────────────────────────────────────────────────────────

# Prefix used to build the "Kode Akun" string (e.g. 1.1.8 for Aset)
KATEGORI_PREFIX = {
    'aset': '1',
    'kewajiban': '2',
    'ekuitas': '3',
    'pendapatan': '4',
    'beban': '5',
}


def _compute_kode_akun(kategori_id: str, kategori_akun: int | None) -> str:
    """Compute the Kode Akun string from the Lv2 record."""
    prefix = KATEGORI_PREFIX.get(kategori_id, '?')
    if not kategori_akun:
        return f'{prefix}.?.?'

    lv1_kode: str = '?'
    lv2_kode: str = '?'
    if kategori_id == 'aset':
        lv2 = AsetLv2.objects.filter(pk=kategori_akun).select_related('aset').first()
        if lv2:
            lv2_kode = lv2.kode
            lv1_kode = lv2.aset.kode if lv2.aset else '?'
    elif kategori_id == 'kewajiban':
        lv2 = KewajibanLv2.objects.filter(pk=kategori_akun).select_related('kewajiban').first()
        if lv2:
            lv2_kode = lv2.kode
            lv1_kode = lv2.kewajiban.kode if lv2.kewajiban else '?'
    elif kategori_id == 'ekuitas':
        lv2 = EkuitasLv2.objects.filter(pk=kategori_akun).select_related('ekuitas').first()
        if lv2:
            lv2_kode = lv2.kode
            lv1_kode = lv2.ekuitas.kode if lv2.ekuitas else '?'

    return f'{prefix}.{lv1_kode}.{lv2_kode}'


class Akun(models.Model):
    KATEGORI_CHOICES = [
        ('aset', 'Aset'),
        ('kewajiban', 'Kewajiban'),
        ('ekuitas', 'Ekuitas'),
        ('pendapatan', 'Pendapatan'),
        ('beban', 'Beban'),
    ]
    kategori_id = models.CharField(max_length=50, choices=KATEGORI_CHOICES, db_index=True)
    kategori_akun = models.BigIntegerField(null=True, blank=True, db_index=True)
    nama = models.CharField(max_length=255, blank=True, default='')
    kode_akun = models.CharField(max_length=50, blank=True, default='', db_index=True)

    class Meta:
        verbose_name = 'Akun'
        verbose_name_plural = 'Akun'
        indexes = [
            # Composite index for chart-of-accounts lookups by category + sub-category
            models.Index(fields=['kategori_id', 'kategori_akun'], name='idx_akun_kategori'),
        ]

    def __str__(self) -> str:
        return f'{self.kode_akun} - {self.nama}' if self.nama else f'Akun {self.id} ({self.kategori_id})'

    def get_lv2_url(self) -> str | None:
        """Return the URL to the associated Lv1 detail page (which lists Lv2 records), or None."""
        from django.urls import reverse
        if not self.kategori_akun:
            return None
        if self.kategori_id == 'aset':
            lv1_pk = AsetLv2.objects.filter(pk=self.kategori_akun).values_list('aset_id', flat=True).first()
            if lv1_pk:
                return reverse('master_data:aset_lv1_detail', args=[lv1_pk])
        elif self.kategori_id == 'kewajiban':
            lv1_pk = KewajibanLv2.objects.filter(pk=self.kategori_akun).values_list('kewajiban_id', flat=True).first()
            if lv1_pk:
                return reverse('master_data:kewajiban_lv1_detail', args=[lv1_pk])
        elif self.kategori_id == 'ekuitas':
            lv1_pk = EkuitasLv2.objects.filter(pk=self.kategori_akun).values_list('ekuitas_id', flat=True).first()
            if lv1_pk:
                return reverse('master_data:ekuitas_lv1_detail', args=[lv1_pk])
        return None


# ── TipeTransaksi ─────────────────────────────────────────────────────────────

class TipeTransaksi(models.Model):
    kode_transaksi = models.CharField(max_length=50, unique=True)
    nama = models.CharField(max_length=255)

    class Meta:
        verbose_name = 'Tipe Transaksi'
        verbose_name_plural = 'Tipe Transaksi'

    def __str__(self) -> str:
        return f'{self.kode_transaksi} - {self.nama}'


# ── Bukti ─────────────────────────────────────────────────────────────────────

class Bukti(models.Model):
    referensi_eksternal = models.CharField(max_length=100)
    tipe_dokumen = models.CharField(max_length=50)
    filepath = models.CharField(max_length=512)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file_hash = models.CharField(max_length=256)

    class Meta:
        verbose_name = 'Bukti'
        verbose_name_plural = 'Bukti'
        indexes = [
            # Document lookups by external reference + type
            models.Index(fields=['referensi_eksternal', 'tipe_dokumen'], name='idx_bukti_ref_tipe'),
            # Duplicate-detection by file hash
            models.Index(fields=['file_hash'], name='idx_bukti_hash'),
        ]

    def __str__(self) -> str:
        return f'{self.tipe_dokumen} - {self.referensi_eksternal}'
