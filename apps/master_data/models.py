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

    class Meta:
        verbose_name = 'Akun'
        verbose_name_plural = 'Akun'
        indexes = [
            # Composite index for chart-of-accounts lookups by category + sub-category
            models.Index(fields=['kategori_id', 'kategori_akun'], name='idx_akun_kategori'),
        ]

    @property
    def kode_akun(self) -> str:
        """Return the computed 'Kode Akun' e.g. 1.1.8, 2.1.3, 3.1.1."""
        prefix = KATEGORI_PREFIX.get(self.kategori_id, '?')
        return f'{prefix}.{self.kategori_id_lv1}.{self.kategori_akun}'

    @property
    def kategori_id_lv1(self) -> int | str:
        """Return the Lv1 id by looking up the source Lv2 record."""
        if self.kategori_id == 'aset' and self.kategori_akun:
            lv2 = AsetLv2.objects.filter(pk=self.kategori_akun).select_related('aset').first()
            return lv2.aset_id if lv2 and lv2.aset_id else '?'
        if self.kategori_id == 'kewajiban' and self.kategori_akun:
            lv2 = KewajibanLv2.objects.filter(pk=self.kategori_akun).select_related('kewajiban').first()
            return lv2.kewajiban_id if lv2 and lv2.kewajiban_id else '?'
        if self.kategori_id == 'ekuitas' and self.kategori_akun:
            lv2 = EkuitasLv2.objects.filter(pk=self.kategori_akun).select_related('ekuitas').first()
            return lv2.ekuitas_id if lv2 and lv2.ekuitas_id else '?'
        return '?'

    def __str__(self) -> str:
        return f'{self.kode_akun} - {self.nama}' if self.nama else f'Akun {self.id} ({self.kategori_id})'


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
