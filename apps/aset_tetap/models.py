"""Aset Tetap (Fixed Assets) models."""
from django.db import models
from django.utils import timezone


def _next_event_number(model_cls, field_name, prefix):
    """Nomor urut event: PREFIX + 3-digit sequence, dengan select_for_update."""
    from django.db import transaction as db_transaction
    with db_transaction.atomic():
        last = (
            model_cls.objects.select_for_update()
            .filter(**{f'{field_name}__startswith': prefix})
            .order_by(f'-{field_name}')
            .values_list(field_name, flat=True)
            .first()
        )
        if last:
            try:
                seq = int(last.rsplit('-', 1)[1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1
        return f'{prefix}{seq:03d}'


class LokasiAset(models.Model):
    """Lokasi fisik aset — terpisah dari dimensi akuntansi (EntitasBisnis)."""
    kode = models.CharField(max_length=50, unique=True, verbose_name='Kode Lokasi')
    nama = models.CharField(max_length=255, verbose_name='Nama Lokasi')
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis', on_delete=models.PROTECT,
        null=True, blank=True, related_name='lokasi_aset', verbose_name='Entitas Bisnis',
    )
    alamat = models.TextField(blank=True, verbose_name='Alamat')
    is_active = models.BooleanField(default=True, verbose_name='Aktif')

    class Meta:
        verbose_name = 'Lokasi Aset'
        verbose_name_plural = 'Lokasi Aset'
        ordering = ['kode']

    def __str__(self) -> str:
        return f'{self.kode} - {self.nama}'


class AsetTetapRecord(models.Model):
    """Fixed asset record — one entry per purchased fixed asset item."""
    KONDISI_CHOICES = [
        ('baik', 'Baik'),
        ('rusak_ringan', 'Rusak Ringan'),
        ('rusak_berat', 'Rusak Berat'),
        ('dalam_perbaikan', 'Dalam Perbaikan'),
    ]
    METODE_PENYUSUTAN_CHOICES = [
        ('straight_line', 'Garis Lurus (Straight Line)'),
        ('double_declining', 'Saldo Menurun (Double Declining Balance)'),
        ('sum_of_years', 'Jumlah Angka Tahun (Sum of The Year Digit)'),
        ('service_hours', 'Satuan Jam Kerja (Service Hours)'),
        ('units_of_production', 'Satuan Hasil Produksi (Productive Output)'),
    ]
    STATUS_CHOICES = [
        ('aktif', 'Aktif'),
        ('dilepas', 'Dilepas'),
    ]

    aset_number = models.CharField(
        max_length=50,
        unique=True,
        editable=False,
        verbose_name='Nomor Aset',
    )
    item = models.ForeignKey(
        'purchase.ItemMasterPurchase',
        on_delete=models.PROTECT,
        related_name='aset_tetap_records',
        verbose_name='Item Master',
        limit_choices_to={'tipe_item': 'ATP'},
    )
    purchase_item = models.ForeignKey(
        'purchase.PurchaseItem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='aset_tetap_records',
        verbose_name='Purchase Item',
    )
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.PROTECT,
        related_name='aset_tetap_records',
        verbose_name='Entitas Bisnis',
    )
    quantity = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        default=1,
        verbose_name='Quantity',
    )
    harga_perolehan = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        verbose_name='Harga Perolehan',
    )
    total_value = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        editable=False,
        default=0,
        verbose_name='Nilai Perolehan',
    )
    akumulasi_penyusutan = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        default=0,
        verbose_name='Akumulasi Penyusutan',
    )
    nilai_residu = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        default=0,
        verbose_name='Nilai Residu',
        help_text='Nilai sisa aset di akhir masa manfaat.',
    )
    estimasi_jam_kerja = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Estimasi Total Jam Kerja',
        help_text='Total estimasi jam kerja selama masa manfaat (untuk metode Service Hours).',
    )
    estimasi_unit_produksi = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Estimasi Total Unit Produksi',
        help_text='Total estimasi unit produksi selama masa manfaat (untuk metode Units of Production).',
    )
    tanggal_perolehan = models.DateField(
        db_index=True,
        default=timezone.now,
        verbose_name='Tanggal Perolehan',
    )
    masa_manfaat = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Masa Manfaat (Tahun)',
        help_text='Override masa manfaat dari item master. Kosongkan untuk menggunakan nilai item master.',
    )
    metode_penyusutan = models.CharField(
        max_length=30,
        choices=METODE_PENYUSUTAN_CHOICES,
        blank=True,
        default='',
        verbose_name='Metode Penyusutan',
        help_text='Override metode penyusutan dari item master.',
    )
    lokasi_legacy = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Lokasi (Legacy)',
        help_text='Lokasi free-text lama sebelum migrasi ke master Lokasi Aset.',
    )
    lokasi_aset = models.ForeignKey(
        'LokasiAset',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='aset_records',
        verbose_name='Lokasi Aset',
    )
    departemen = models.ForeignKey(
        'entitas_bisnis.EntitasBisnisLv3',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='aset_records',
        verbose_name='Departemen',
    )
    pic = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Penanggung Jawab (PIC)',
    )
    kondisi = models.CharField(
        max_length=20,
        choices=KONDISI_CHOICES,
        default='baik',
        verbose_name='Kondisi Aset',
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='aktif',
        db_index=True,
        verbose_name='Status Aset',
    )
    keterangan = models.TextField(
        blank=True,
        verbose_name='Keterangan',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Aset Tetap Record'
        verbose_name_plural = 'Aset Tetap Records'
        ordering = ['-tanggal_perolehan', '-created_at']
        indexes = [
            models.Index(fields=['item', 'tanggal_perolehan'], name='idx_atr_item_tanggal'),
            models.Index(fields=['entitas_bisnis', 'tanggal_perolehan'], name='idx_atr_eb_tanggal'),
            models.Index(fields=['aset_number'], name='idx_atr_number'),
        ]

    def __str__(self) -> str:
        return self.aset_number

    @property
    def nilai_buku(self):
        return self.total_value - self.akumulasi_penyusutan

    def save(self, *args, **kwargs):
        self.total_value = self.quantity * self.harga_perolehan
        if not self.aset_number:
            self.aset_number = self._generate_aset_number()
        super().save(*args, **kwargs)

    def _generate_aset_number(self) -> str:
        """Generate sequential aset number: ATP-XXXX-YYY."""
        item_suffix = self.item.item_id.split('-', 1)[1] if '-' in self.item.item_id else '0001'
        pattern = f'ATP-{item_suffix}-'

        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            last = (
                AsetTetapRecord.objects
                .select_for_update()
                .filter(aset_number__startswith=pattern)
                .order_by('-aset_number')
                .values_list('aset_number', flat=True)
                .first()
            )
            if last:
                try:
                    seq = int(last.rsplit('-', 1)[1]) + 1
                except (ValueError, IndexError):
                    seq = 1
            else:
                seq = 1
            return f'{pattern}{seq:03d}'


class AssetDisposal(models.Model):
    """Peristiwa pelepasan aset tetap — memicu jurnal pelepasan & laba/rugi."""
    JENIS_CHOICES = [
        ('jual', 'Jual'),
        ('hibah', 'Hibah'),
        ('rusak', 'Rusak'),
        ('musnah', 'Musnah'),
    ]

    disposal_number = models.CharField(max_length=50, unique=True, editable=False, verbose_name='Nomor Pelepasan')
    aset = models.ForeignKey('AsetTetapRecord', on_delete=models.PROTECT, related_name='disposals', verbose_name='Aset')
    tanggal = models.DateField(default=timezone.now, db_index=True, verbose_name='Tanggal Pelepasan')
    jenis = models.CharField(max_length=10, choices=JENIS_CHOICES, verbose_name='Jenis Pelepasan')
    quantity = models.DecimalField(max_digits=15, decimal_places=4, verbose_name='Quantity Dilepas')
    harga_jual = models.DecimalField(max_digits=19, decimal_places=4, default=0, verbose_name='Harga Jual')
    akun_kas = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT, null=True, blank=True,
        related_name='disposal_kas', verbose_name='Akun Kas/Piutang',
    )
    akun_laba_rugi = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='disposal_laba_rugi', verbose_name='Akun Laba/Rugi Pelepasan',
    )
    perolehan_dilepas = models.DecimalField(max_digits=19, decimal_places=4, editable=False, default=0)
    akumulasi_dilepas = models.DecimalField(max_digits=19, decimal_places=4, editable=False, default=0)
    residu_dilepas = models.DecimalField(max_digits=19, decimal_places=4, editable=False, default=0)
    laba_rugi = models.DecimalField(max_digits=19, decimal_places=4, editable=False, default=0)
    jurnal_header = models.ForeignKey(
        'jurnal.JurnalHeader', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    keterangan = models.TextField(blank=True, verbose_name='Keterangan')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Pelepasan Aset'
        verbose_name_plural = 'Pelepasan Aset'
        ordering = ['-tanggal', '-created_at']
        indexes = [
            models.Index(fields=['aset', 'tanggal'], name='idx_disposal_aset_tgl'),
        ]

    def __str__(self) -> str:
        return self.disposal_number

    def save(self, *args, **kwargs):
        if not self.disposal_number:
            self.disposal_number = self._generate_disposal_number()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_disposal_number() -> str:
        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            last = (
                AssetDisposal.objects
                .select_for_update()
                .filter(disposal_number__startswith='DSP-')
                .order_by('-disposal_number')
                .values_list('disposal_number', flat=True)
                .first()
            )
            if last:
                try:
                    seq = int(last.rsplit('-', 1)[1]) + 1
                except (ValueError, IndexError):
                    seq = 1
            else:
                seq = 1
            return f'DSP-{seq:03d}'


class AssetMaintenance(models.Model):
    """Peristiwa pemeliharaan aset — memicu jurnal beban."""
    JENIS_CHOICES = [('rutin', 'Rutin'), ('perbaikan', 'Perbaikan'), ('servis', 'Servis')]

    maintenance_number = models.CharField(max_length=50, unique=True, editable=False, verbose_name='Nomor Maintenance')
    aset = models.ForeignKey('AsetTetapRecord', on_delete=models.PROTECT, related_name='maintenances', verbose_name='Aset')
    tanggal = models.DateField(default=timezone.now, db_index=True, verbose_name='Tanggal')
    jenis = models.CharField(max_length=10, choices=JENIS_CHOICES, verbose_name='Jenis')
    vendor = models.CharField(max_length=255, blank=True, verbose_name='Vendor')
    biaya = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Biaya')
    akun_beban = models.ForeignKey('master_data.Akun', on_delete=models.PROTECT, related_name='mtn_beban', verbose_name='Akun Beban Pemeliharaan')
    akun_kas_utang = models.ForeignKey('master_data.Akun', on_delete=models.PROTECT, related_name='mtn_kas', verbose_name='Akun Kas/Utang')
    kondisi_setelah = models.CharField(max_length=20, choices=AsetTetapRecord.KONDISI_CHOICES, blank=True, verbose_name='Kondisi Setelah')
    kondisi_sebelum = models.CharField(max_length=20, blank=True, editable=False)
    jurnal_header = models.ForeignKey('jurnal.JurnalHeader', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    keterangan = models.TextField(blank=True, verbose_name='Keterangan')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Maintenance Aset'
        verbose_name_plural = 'Maintenance Aset'
        ordering = ['-tanggal', '-created_at']

    def __str__(self) -> str:
        return self.maintenance_number

    def save(self, *args, **kwargs):
        if not self.maintenance_number:
            self.maintenance_number = _next_event_number(AssetMaintenance, 'maintenance_number', 'MTN-')
        super().save(*args, **kwargs)
