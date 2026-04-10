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

class Akun(models.Model):
    KATEGORI_CHOICES = [
        ('aset', 'Aset'),
        ('kewajiban', 'Kewajiban'),
        ('ekuitas', 'Ekuitas'),
        ('pendapatan', 'Pendapatan'),
        ('beban', 'Beban'),
    ]
    kategori_id = models.CharField(max_length=50, choices=KATEGORI_CHOICES)
    kategori_akun = models.BigIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = 'Akun'
        verbose_name_plural = 'Akun'

    def __str__(self) -> str:
        return f'Akun {self.id} ({self.kategori_id})'


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

    def __str__(self) -> str:
        return f'{self.tipe_dokumen} - {self.referensi_eksternal}'
