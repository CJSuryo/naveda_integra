from decimal import Decimal
from django.conf import settings
from django.db import models


JENIS_PAJAK_CHOICES = [
    ('ppn_umum',              'PPN Umum (BKP/JKP non-mewah)'),
    ('ppn_mewah',             'PPN Mewah (BKP Mewah 12%)'),
    ('ppn_ekspor',            'PPN Ekspor (0%)'),
    ('ppn_bm',                'PPnBM'),
    ('pph_23_jasa',           'PPh 23 Jasa (2%)'),
    ('pph_23_royalti',        'PPh 23 Royalti (15%)'),
    ('pph_23_dividen',        'PPh 23 Dividen (15%)'),
    ('pph_21_bukan_pegawai',  'PPh 21 Bukan Pegawai (progresif)'),
    ('pph_4_2_sewa',          'PPh 4(2) Sewa Tanah/Bangunan (10%)'),
    ('pph_4_2_bunga',         'PPh 4(2) Bunga Deposito (20%)'),
    ('pph_umkm',              'PPh Final UMKM (0,5%)'),
]

SOURCE_TYPE_CHOICES = [
    ('pendapatan_kp', 'Pendapatan — Kewajiban Pelaksanaan'),
    ('sales_item',    'Sales Item'),
    ('retur_customer_item', 'Retur Pelanggan — Item'),
    ('purchase_item', 'Purchase Item'),
    ('piutang_item',  'Piutang Item'),
    ('utang_item',    'Utang Item'),
]

SIFAT_PAJAK_CHOICES = [
    ('potong_pungut', 'Potong/Pungut — Dr akun_lawan | Cr akun_pajak'),
    ('prepaid',       'Prepaid/Dipotong Lawan — Dr akun_pajak | Cr akun_lawan'),
]

STATUS_CHOICES = [
    ('draft',      'Draft'),
    ('final',      'Final'),
    ('disetor',    'Disetor'),
    ('dibatalkan', 'Dibatalkan'),
]


class TarifPajak(models.Model):
    jenis_pajak    = models.CharField(max_length=40, choices=JENIS_PAJAK_CHOICES, db_index=True)
    nama           = models.CharField(max_length=100)
    tarif_persen   = models.DecimalField(max_digits=7, decimal_places=4)
    faktor_dpp     = models.DecimalField(
        max_digits=7, decimal_places=6, default=Decimal('1.000000'),
        help_text='Pengali DPP sebelum tarif diterapkan. ppn_umum (PMK 131/2024): 11/12 ≈ 0.916667',
    )
    berlaku_mulai  = models.DateField()
    berlaku_sampai = models.DateField(null=True, blank=True)
    keterangan     = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Tarif Pajak'
        verbose_name_plural = 'Tarif Pajak'
        indexes = [
            models.Index(fields=['jenis_pajak', 'berlaku_mulai'], name='idx_tarif_jenis_mulai'),
        ]

    def __str__(self):
        return f'{self.get_jenis_pajak_display()} — {self.tarif_persen}% (berlaku {self.berlaku_mulai})'


class BracketPPhOP(models.Model):
    batas_bawah   = models.DecimalField(max_digits=19, decimal_places=0)
    batas_atas    = models.DecimalField(max_digits=19, decimal_places=0, null=True, blank=True)
    tarif_persen  = models.DecimalField(max_digits=5, decimal_places=2)
    berlaku_mulai = models.DateField()

    class Meta:
        verbose_name = 'Bracket PPh OP'
        verbose_name_plural = 'Bracket PPh OP'
        ordering = ['berlaku_mulai', 'batas_bawah']

    def __str__(self):
        atas = f'{int(self.batas_atas):,}' if self.batas_atas else '∞'
        return f'{int(self.batas_bawah):,} – {atas} → {self.tarif_persen}%'


class MasaPajak(models.Model):
    tahun  = models.PositiveSmallIntegerField()
    bulan  = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=10, choices=[('open', 'Open'), ('locked', 'Locked')], default='open')

    class Meta:
        verbose_name = 'Masa Pajak'
        verbose_name_plural = 'Masa Pajak'
        unique_together = ('tahun', 'bulan')
        ordering = ['-tahun', '-bulan']

    def __str__(self):
        return f'{self.tahun}-{self.bulan:02d} ({self.status})'


class PajakTransaksi(models.Model):
    source_type    = models.CharField(max_length=40, choices=SOURCE_TYPE_CHOICES, db_index=True)
    source_id      = models.PositiveIntegerField(db_index=True)
    masa_pajak     = models.DateField(db_index=True)
    jenis_pajak    = models.CharField(max_length=40, choices=JENIS_PAJAK_CHOICES)
    dpp            = models.DecimalField(max_digits=19, decimal_places=4)
    tarif_persen   = models.DecimalField(max_digits=7, decimal_places=4)
    jumlah_pajak   = models.DecimalField(max_digits=19, decimal_places=4)
    sifat_pajak    = models.CharField(max_length=20, choices=SIFAT_PAJAK_CHOICES)
    status         = models.CharField(max_length=15, choices=STATUS_CHOICES, default='draft')
    is_overridden  = models.BooleanField(default=False)
    akun_pajak     = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='pajak_transaksi_pajak_set',
    )
    akun_lawan     = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='pajak_transaksi_lawan_set',
    )
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pajak_transaksi_set',
    )
    jurnal_header  = models.ForeignKey(
        'jurnal.JurnalHeader', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pajak_transaksi_set',
    )
    created_at     = models.DateTimeField(auto_now_add=True)
    modified_by    = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pajak_transaksi_modified_set',
    )
    modified_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Pajak Transaksi'
        verbose_name_plural = 'Pajak Transaksi'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['source_type', 'source_id'], name='idx_pajak_trx_source'),
            models.Index(fields=['masa_pajak', 'jenis_pajak'], name='idx_pajak_trx_masa_jenis'),
            models.Index(fields=['status'], name='idx_pajak_trx_status'),
        ]

    def __str__(self):
        return f'{self.get_jenis_pajak_display()} — {self.source_type}:{self.source_id} — {self.jumlah_pajak}'
