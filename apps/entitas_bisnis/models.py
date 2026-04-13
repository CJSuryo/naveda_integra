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
        verbose_name = 'Entitas Bisnis Level 1'
        verbose_name_plural = 'Entitas Bisnis Level 1'
        indexes = [
            # Active-entity filtering (dashboards, dropdowns)
            models.Index(fields=['status_aktif', 'nama'], name='idx_eb_aktif_nama'),
            # Per-type lookups
            models.Index(fields=['tipe_entitas', 'status_aktif'], name='idx_eb_tipe_aktif'),
        ]

    def __str__(self) -> str:
        return self.nama


class EntitasBisnisLv2(models.Model):
    """Level 2 of business entity hierarchy."""
    entitas_bisnis = models.ForeignKey(
        EntitasBisnis,
        on_delete=models.CASCADE,
        related_name='children_lv2',
        verbose_name='Entitas Bisnis Level 1',
    )
    nama = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    telepon = models.CharField(max_length=50, blank=True, null=True)
    alamat_lengkap = models.TextField(blank=True, null=True)
    tanggal_bergabung = models.DateField(blank=True, null=True)
    status_aktif = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Entitas Bisnis Level 2'
        verbose_name_plural = 'Entitas Bisnis Level 2'
        indexes = [
            models.Index(fields=['entitas_bisnis', 'status_aktif'], name='idx_eblv2_entitas_aktif'),
        ]

    def __str__(self) -> str:
        return f'{self.nama} ({self.entitas_bisnis.nama})'


class EntitasBisnisLv3(models.Model):
    """Level 3 of business entity hierarchy."""
    parent_lv2 = models.ForeignKey(
        EntitasBisnisLv2,
        on_delete=models.CASCADE,
        related_name='children_lv3',
        verbose_name='Entitas Bisnis Level 2',
    )
    nama = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    telepon = models.CharField(max_length=50, blank=True, null=True)
    alamat_lengkap = models.TextField(blank=True, null=True)
    tanggal_bergabung = models.DateField(blank=True, null=True)
    status_aktif = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Entitas Bisnis Level 3'
        verbose_name_plural = 'Entitas Bisnis Level 3'
        indexes = [
            models.Index(fields=['parent_lv2', 'status_aktif'], name='idx_eblv3_parent_aktif'),
        ]

    def __str__(self) -> str:
        return f'{self.nama} ({self.parent_lv2.nama})'
