"""EntitasBisnis models."""
from django.conf import settings
from django.db import models


class TipeEntitas(models.Model):
    """Business-type lookup (e.g. FnB, Laundry, Restaurant, Hotel)."""
    nama = models.CharField(max_length=255, unique=True)

    class Meta:
        verbose_name = 'Tipe Entitas'
        verbose_name_plural = 'Tipe Entitas'

    def __str__(self) -> str:
        return self.nama


class EntitasBisnis(models.Model):
    RELASI_CHOICES = [
        ('pelanggan', 'Pelanggan'),
        ('pemasok', 'Pemasok'),
        ('keduanya', 'Keduanya'),
    ]

    nama = models.CharField(max_length=255)
    tipe_entitas = models.ForeignKey(
        TipeEntitas,
        on_delete=models.PROTECT,
        related_name='entitas_bisnis_set',
        verbose_name='Tipe Entitas',
    )
    relasi = models.CharField(
        max_length=50,
        choices=RELASI_CHOICES,
        default='pelanggan',
        verbose_name='Relasi Bisnis',
    )
    email = models.EmailField(blank=True, null=True)
    telepon = models.CharField(max_length=50, blank=True, null=True)
    alamat_lengkap = models.TextField(blank=True, null=True)
    tax_id = models.CharField(max_length=50, unique=True, blank=True, null=True)
    tanggal_bergabung = models.DateField(blank=True, null=True)
    status_aktif = models.BooleanField(default=True)
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='entitas_bisnis_owned',
        blank=True,
        verbose_name='Users',
    )

    class Meta:
        verbose_name = 'Entitas Bisnis'
        verbose_name_plural = 'Entitas Bisnis'

    def __str__(self) -> str:
        return self.nama


class CabangEntitasBisnis(models.Model):
    """Branch of a business entity."""
    entitas_bisnis = models.ForeignKey(
        EntitasBisnis,
        on_delete=models.CASCADE,
        related_name='cabang_set',
        verbose_name='Entitas Bisnis',
    )
    nama = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    telepon = models.CharField(max_length=50, blank=True, null=True)
    alamat_lengkap = models.TextField(blank=True, null=True)
    tanggal_bergabung = models.DateField(blank=True, null=True)
    status_aktif = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Cabang Entitas Bisnis'
        verbose_name_plural = 'Cabang Entitas Bisnis'

    def __str__(self) -> str:
        return f'{self.nama} ({self.entitas_bisnis.nama})'
