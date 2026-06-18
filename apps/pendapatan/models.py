from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


KATEGORI_CHOICES = [
    ('sewa', 'Sewa'),
    ('jasa', 'Jasa'),
    ('bunga', 'Bunga'),
    ('dividen', 'Dividen'),
    ('komisi', 'Komisi'),
    ('royalti', 'Royalti'),
    ('management_fee', 'Management Fee'),
    ('penjualan_aset', 'Penjualan Aset'),
    ('lainnya', 'Lainnya'),
]

DEFERRED_METODE_CHOICES = [
    ('straight_line', 'Garis Lurus'),
    ('custom', 'Custom'),
]

TAX_TYPE_CHOICES = [
    ('ppn_keluaran', 'PPN Keluaran'),
    ('pph_23', 'PPh 23'),
    ('pph_21', 'PPh 21'),
    ('pph_4_2', 'PPh 4(2)'),
]

TAX_PAYMENT_CHOICES = [
    ('belum_transfer', 'Belum Transfer'),
    ('sudah_transfer', 'Sudah Transfer'),
]


class StandarAkuntansi(models.TextChoices):
    PSAK_71_72 = 'PSAK_71_72', 'PSAK 71/72'
    SAK_ETAP = 'SAK_ETAP', 'SAK ETAP'


class PendapatanHeader(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('confirmed', 'Dikonfirmasi'),
        ('voided', 'Dibatalkan'),
    ]
    SOURCE_TYPE_CHOICES = [
        ('manual', 'Manual'),
        ('from_sales', 'Dari Sales'),
        ('recurring', 'Recurring'),
    ]

    transaction_id = models.CharField(max_length=100, unique=True, editable=False, verbose_name='ID Transaksi')
    tanggal = models.DateField(db_index=True, default=timezone.now, verbose_name='Tanggal')
    deskripsi = models.TextField(blank=True, default='', verbose_name='Deskripsi')
    source_type = models.CharField(
        max_length=20, choices=SOURCE_TYPE_CHOICES, default='manual', verbose_name='Sumber',
    )
    source_sales = models.ForeignKey(
        'sales.SalesHeader', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pendapatan_headers', verbose_name='Sales Header',
    )
    source_recurring = models.ForeignKey(
        'pendapatan.RecurringTemplate', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='generated_headers', verbose_name='Recurring Template',
    )
    payment_type = models.CharField(
        max_length=10,
        choices=[('cash', 'Cash'), ('credit', 'Kredit')],
        default='cash',
        verbose_name='Tipe Pembayaran',
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name='Status',
    )
    is_locked = models.BooleanField(default=False, verbose_name='Terkunci')
    standar_akuntansi = models.CharField(
        max_length=20,
        choices=StandarAkuntansi.choices,
        default=StandarAkuntansi.PSAK_71_72,
        verbose_name='Standar Akuntansi',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pendapatan_created', verbose_name='Dibuat Oleh',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Pendapatan Header'
        verbose_name_plural = 'Pendapatan Header'
        ordering = ['-tanggal', '-created_at']
        indexes = [
            models.Index(fields=['tanggal', 'status'], name='idx_pendh_tanggal_status'),
        ]

    def __str__(self) -> str:
        return self.transaction_id

    def save(self, *args, **kwargs):
        if not self.transaction_id:
            self.transaction_id = self._generate_transaction_id()
        super().save(*args, **kwargs)

    def _generate_transaction_id(self) -> str:
        from django.db import transaction as db_transaction
        prefix = 'TRX-PND'
        with db_transaction.atomic():
            last = (
                PendapatanHeader.objects
                .select_for_update()
                .filter(transaction_id__startswith=f'{prefix}-')
                .order_by('-transaction_id')
                .values_list('transaction_id', flat=True)
                .first()
            )
            seq = 1
            if last:
                try:
                    seq = int(last.rsplit('-', 1)[1]) + 1
                except (ValueError, IndexError):
                    seq = 1
            return f'{prefix}-{seq:03d}'


class PendapatanEntitasBisnis(models.Model):
    pendapatan_header = models.ForeignKey(
        PendapatanHeader, on_delete=models.CASCADE, related_name='entitas_groups',
        verbose_name='Pendapatan Header',
    )
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis', on_delete=models.PROTECT,
        related_name='pendapatan_groups', verbose_name='Entitas Bisnis',
    )
    entitas_bisnis_lv2 = models.ForeignKey(
        'entitas_bisnis.EntitasBisnisLv2', on_delete=models.PROTECT,
        null=True, blank=True, related_name='pendapatan_groups', verbose_name='EB Lv2',
    )
    entitas_bisnis_lv3 = models.ForeignKey(
        'entitas_bisnis.EntitasBisnisLv3', on_delete=models.PROTECT,
        null=True, blank=True, related_name='pendapatan_groups', verbose_name='EB Lv3',
    )
    payment_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        null=True, blank=True, related_name='pendapatan_eb_payment', verbose_name='Akun Pembayaran',
    )

    class Meta:
        verbose_name = 'Pendapatan Entitas Bisnis'
        verbose_name_plural = 'Pendapatan Entitas Bisnis'
        indexes = [
            models.Index(fields=['pendapatan_header', 'entitas_bisnis'], name='idx_pend_eb_header_eb'),
        ]

    def __str__(self) -> str:
        return f'{self.pendapatan_header.transaction_id} → {self.entitas_bisnis.nama}'


class KewajibabPelaksanaan(models.Model):
    class RecognitionType(models.TextChoices):
        POINT_IN_TIME = 'point_in_time', 'Point-in-Time'
        OVER_TIME = 'over_time', 'Over Time'

    pendapatan_eb = models.ForeignKey(
        PendapatanEntitasBisnis, on_delete=models.CASCADE, related_name='items',
        verbose_name='Pendapatan EB Group',
    )
    deskripsi_item = models.TextField(verbose_name='Deskripsi Item')
    kategori = models.CharField(max_length=30, choices=KATEGORI_CHOICES, verbose_name='Kategori')
    sub_transaction_type = models.ForeignKey(
        'purchase.SubTransactionType', on_delete=models.PROTECT,
        related_name='pendapatan_items', verbose_name='Sub-Tipe Transaksi',
    )
    jumlah_bruto = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Jumlah Bruto')
    revenue_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='pendapatan_item_revenue', verbose_name='Akun Pendapatan',
    )
    payment_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        null=True, blank=True, related_name='pendapatan_item_payment', verbose_name='Akun Pembayaran',
    )
    tax = models.DecimalField(max_digits=19, decimal_places=4, null=True, blank=True, verbose_name='Pajak (Nominal)')
    tax_type = models.CharField(max_length=30, choices=TAX_TYPE_CHOICES, blank=True, default='', verbose_name='Tipe Pajak')
    tax_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        null=True, blank=True, related_name='pendapatan_item_tax', verbose_name='Akun Pajak',
    )
    tax_payment = models.CharField(max_length=20, choices=TAX_PAYMENT_CHOICES, blank=True, default='', verbose_name='Status Transfer Pajak')
    tax_payment_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        null=True, blank=True, related_name='pendapatan_item_tax_payment', verbose_name='Akun Utang Pajak',
    )
    is_deferred = models.BooleanField(default=False, verbose_name='Pendapatan Diterima di Muka')
    deferred_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        null=True, blank=True, related_name='pendapatan_item_deferred', verbose_name='Akun Deferred (Liability)',
    )
    recognition_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        null=True, blank=True, related_name='pendapatan_item_recognition', verbose_name='Akun Pengakuan',
    )
    deferred_tanggal_mulai = models.DateField(null=True, blank=True, verbose_name='Tanggal Mulai Pengakuan')
    deferred_tanggal_selesai = models.DateField(null=True, blank=True, verbose_name='Tanggal Selesai Pengakuan')
    deferred_metode = models.CharField(
        max_length=20, choices=DEFERRED_METODE_CHOICES, blank=True, default='straight_line',
        verbose_name='Metode Pengakuan',
    )
    # PSAK 72 fields
    harga_j = models.DecimalField(
        max_digits=19, decimal_places=4, default=0,
        verbose_name='Harga Alokasi (PSAK 72)',
    )
    recognition_type = models.CharField(
        max_length=20,
        choices=RecognitionType.choices,
        default=RecognitionType.POINT_IN_TIME,
        verbose_name='Tipe Pengakuan',
    )
    # Over-time staging fields (set by form, consumed at confirm)
    ot_tipe_aliran = models.CharField(max_length=30, blank=True, default='', verbose_name='Tipe Aliran')
    ot_progress_method = models.CharField(max_length=30, blank=True, default='', verbose_name='Metode Progress')
    ot_tanggal_mulai = models.DateField(null=True, blank=True, verbose_name='Tanggal Mulai OT')
    ot_tanggal_selesai = models.DateField(null=True, blank=True, verbose_name='Tanggal Selesai OT')
    ot_liabilitas_kontrak_acct = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        null=True, blank=True, related_name='+',
        verbose_name='Akun Liabilitas Kontrak',
    )
    ot_aset_kontrak_acct = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        null=True, blank=True, related_name='+',
        verbose_name='Akun Aset Kontrak',
    )
    ot_biaya_estimasi_total = models.DecimalField(
        max_digits=19, decimal_places=4, null=True, blank=True,
        verbose_name='Biaya Estimasi Total',
    )

    class Meta:
        db_table = 'pendapatan_pendapatanitem'
        verbose_name = 'Kewajiban Pelaksanaan'
        verbose_name_plural = 'Kewajiban Pelaksanaan'
        indexes = [
            models.Index(fields=['pendapatan_eb'], name='idx_pend_pi_eb'),
            models.Index(fields=['sub_transaction_type'], name='idx_pend_pi_stt'),
        ]

    def __str__(self) -> str:
        return f'{self.pendapatan_eb.pendapatan_header.transaction_id} — {self.deskripsi_item[:40]}'


# Backward-compat alias — remove after all references updated in Task 9
PendapatanItem = KewajibabPelaksanaan


class PendapatanEventLog(models.Model):
    EVENT_CHOICES = [
        ('CREATED', 'Dibuat'),
        ('CONFIRMED', 'Dikonfirmasi'),
        ('VOIDED', 'Dibatalkan'),
        ('JOURNAL_CREATED', 'Jurnal Dibuat'),
        ('PIUTANG_CREATED', 'Piutang Dibuat'),
        ('DEFERRED_SCHEDULED', 'Deferred Dijadwalkan'),
        ('RECURRING_GENERATED', 'Dihasilkan dari Recurring'),
        ('RECOGNIZE', 'Pengakuan Pendapatan'),
        ('JOURNAL_PSAK72', 'Jurnal PSAK 72 Dibuat'),
        ('PIUTANG_CREATED_KP', 'Piutang KP Dibuat'),
        ('ASSET_CONVERTED', 'Aset Kontrak Dikonversi'),
        ('JADWAL_CREATED', 'Jadwal Pengakuan Dibuat'),
    ]

    pendapatan_header = models.ForeignKey(
        PendapatanHeader, on_delete=models.CASCADE, related_name='event_logs',
        verbose_name='Pendapatan Header',
    )
    event_type = models.CharField(max_length=30, choices=EVENT_CHOICES)
    description = models.TextField(blank=True, default='')
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pendapatan_event_logs',
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Event Log Pendapatan'
        verbose_name_plural = 'Event Log Pendapatan'
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['pendapatan_header', 'timestamp'], name='idx_pel_header_ts'),
        ]

    def __str__(self) -> str:
        return f'{self.pendapatan_header.transaction_id} — {self.event_type} @ {self.timestamp}'


class RecurringTemplate(models.Model):
    FREKUENSI_CHOICES = [
        ('harian', 'Harian'),
        ('mingguan', 'Mingguan'),
        ('bulanan', 'Bulanan'),
        ('triwulanan', 'Triwulanan'),
        ('semesteran', 'Semesteran'),
        ('tahunan', 'Tahunan'),
    ]

    nama = models.CharField(max_length=255, verbose_name='Nama Template')
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.PROTECT,
        verbose_name='Entitas Bisnis',
    )
    entitas_bisnis_lv2 = models.ForeignKey(
        'entitas_bisnis.EntitasBisnisLv2',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name='Entitas Bisnis Lv2',
    )
    entitas_bisnis_lv3 = models.ForeignKey(
        'entitas_bisnis.EntitasBisnisLv3',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name='Entitas Bisnis Lv3',
    )
    deskripsi_item = models.TextField(verbose_name='Deskripsi Item')
    kategori = models.CharField(
        max_length=30,
        choices=KATEGORI_CHOICES,
        verbose_name='Kategori',
    )
    sub_transaction_type = models.ForeignKey(
        'purchase.SubTransactionType',
        on_delete=models.PROTECT,
        verbose_name='Sub Transaction Type',
    )
    jumlah = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        verbose_name='Jumlah per Periode',
    )
    revenue_account = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        related_name='recurring_revenue_templates',
        verbose_name='Akun Pendapatan',
    )
    payment_account = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='recurring_payment_templates',
        verbose_name='Akun Pembayaran',
    )
    payment_type = models.CharField(
        max_length=10,
        choices=[('cash', 'Cash'), ('credit', 'Kredit')],
        default='cash',
        verbose_name='Tipe Pembayaran',
    )
    frekuensi = models.CharField(
        max_length=20,
        choices=FREKUENSI_CHOICES,
        verbose_name='Frekuensi',
    )
    tanggal_mulai = models.DateField(verbose_name='Tanggal Mulai')
    tanggal_selesai = models.DateField(
        null=True,
        blank=True,
        verbose_name='Tanggal Selesai',
    )
    tanggal_berikutnya = models.DateField(verbose_name='Tanggal Berikutnya')
    auto_confirm = models.BooleanField(
        default=False,
        verbose_name='Auto Konfirmasi',
    )
    is_active = models.BooleanField(default=True, verbose_name='Aktif')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Dibuat Oleh',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['tanggal_berikutnya']
        verbose_name = 'Recurring Template'
        verbose_name_plural = 'Recurring Templates'

    def __str__(self):
        return self.nama

    def save(self, *args, **kwargs):
        if not self.pk and self.tanggal_mulai and not self.tanggal_berikutnya:
            self.tanggal_berikutnya = self.tanggal_mulai
        super().save(*args, **kwargs)


class DeferredRevenueSchedule(models.Model):
    pendapatan_item = models.OneToOneField(
        PendapatanItem, on_delete=models.CASCADE, related_name='deferred_schedule',
        verbose_name='Pendapatan Item',
    )
    jumlah_total = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Jumlah Total')
    tanggal_mulai = models.DateField(verbose_name='Tanggal Mulai')
    tanggal_selesai = models.DateField(verbose_name='Tanggal Selesai')
    metode = models.CharField(
        max_length=20, choices=DEFERRED_METODE_CHOICES, default='straight_line',
        verbose_name='Metode',
    )
    recognition_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='deferred_recognition', verbose_name='Akun Pengakuan',
    )
    deferred_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='deferred_liability', verbose_name='Akun Deferred (Liability)',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Jadwal Deferred Revenue'
        verbose_name_plural = 'Jadwal Deferred Revenue'

    def __str__(self) -> str:
        return f'Deferred {self.pendapatan_item.pk} — {self.tanggal_mulai} s/d {self.tanggal_selesai}'

    @property
    def total_recognized(self):
        from decimal import Decimal
        from django.db.models import Sum
        return self.entries.filter(status='recognized').aggregate(s=Sum('jumlah'))['s'] or Decimal('0')

    @property
    def total_remaining(self):
        return self.jumlah_total - self.total_recognized


class DeferredRevenueEntry(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Belum Diakui'),
        ('recognized', 'Sudah Diakui'),
        ('reversed', 'Dibalik'),
    ]

    schedule = models.ForeignKey(
        DeferredRevenueSchedule, on_delete=models.CASCADE, related_name='entries',
        verbose_name='Jadwal',
    )
    periode = models.DateField(verbose_name='Periode (1 = bulan)')
    jumlah = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Jumlah')
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='Status',
    )
    jurnal_header = models.ForeignKey(
        'jurnal.JurnalHeader', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='deferred_entries', verbose_name='Jurnal',
    )

    class Meta:
        verbose_name = 'Entry Deferred Revenue'
        verbose_name_plural = 'Entry Deferred Revenue'
        unique_together = ('schedule', 'periode')
        ordering = ['periode']

    def __str__(self) -> str:
        return f'{self.schedule.pk} — {self.periode.strftime("%Y-%m")} — {self.status}'


class JadwalPengakuan(models.Model):
    class TipeAliran(models.TextChoices):
        ADVANCE_PAYMENT_CASH = 'advance_payment_cash', 'Advance Payment (Cash)'
        PERIODIC_BILLING = 'periodic_billing', 'Periodic Billing'
        PERFORMANCE_FIRST = 'performance_first', 'Performance First'

    class ProgressMethod(models.TextChoices):
        STRAIGHT_LINE = 'straight_line', 'Garis Lurus'
        PERCENTAGE_COMPLETION = 'percentage_completion', 'Persentase Selesai'
        MILESTONE = 'milestone', 'Milestone'

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Aktif'
        COMPLETED = 'completed', 'Selesai'
        VOIDED = 'voided', 'Dibatalkan'

    kp = models.OneToOneField(
        KewajibabPelaksanaan, on_delete=models.CASCADE, related_name='jadwal',
        verbose_name='Kewajiban Pelaksanaan',
    )
    tipe_aliran = models.CharField(
        max_length=30, choices=TipeAliran.choices, verbose_name='Tipe Aliran',
    )
    progress_method = models.CharField(
        max_length=30, choices=ProgressMethod.choices, verbose_name='Metode Progress',
    )
    tanggal_mulai = models.DateField(verbose_name='Tanggal Mulai')
    tanggal_selesai = models.DateField(verbose_name='Tanggal Selesai')
    liabilitas_kontrak_acct = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        null=True, blank=True, related_name='+',
        verbose_name='Akun Liabilitas Kontrak',
    )
    aset_kontrak_acct = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        null=True, blank=True, related_name='+',
        verbose_name='Akun Aset Kontrak',
    )
    biaya_estimasi_total = models.DecimalField(
        max_digits=19, decimal_places=4, null=True, blank=True,
        verbose_name='Biaya Estimasi Total',
    )
    nilai_total = models.DecimalField(
        max_digits=19, decimal_places=4, verbose_name='Nilai Total',
    )
    nilai_diakui = models.DecimalField(
        max_digits=19, decimal_places=4, default=0, verbose_name='Nilai Diakui',
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE, verbose_name='Status',
    )

    class Meta:
        verbose_name = 'Jadwal Pengakuan'
        verbose_name_plural = 'Jadwal Pengakuan'

    @property
    def nilai_belum_diakui(self):
        return self.nilai_total - self.nilai_diakui

    def __str__(self) -> str:
        return f'Jadwal {self.kp_id} [{self.tipe_aliran}]'


class EntriPengakuan(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Belum Diakui'
        RECOGNIZED = 'recognized', 'Sudah Diakui'
        SKIPPED = 'skipped', 'Dilewati'

    jadwal = models.ForeignKey(
        JadwalPengakuan, on_delete=models.CASCADE, related_name='entri',
        verbose_name='Jadwal Pengakuan',
    )
    tanggal_target = models.DateField(verbose_name='Tanggal Target')
    nilai = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Nilai')
    nilai_diakui = models.DecimalField(
        max_digits=19, decimal_places=4, default=0, verbose_name='Nilai Diakui',
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name='Status',
    )
    jurnal_header = models.ForeignKey(
        'jurnal.JurnalHeader', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='entri_pengakuan',
        verbose_name='Jurnal',
    )
    catatan = models.TextField(blank=True, default='', verbose_name='Catatan')

    class Meta:
        ordering = ['tanggal_target']
        verbose_name = 'Entri Pengakuan'
        verbose_name_plural = 'Entri Pengakuan'

    def __str__(self) -> str:
        return f'Entri {self.tanggal_target} — {self.nilai}'


class AsetKontrak(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Aktif'
        CONVERTED = 'converted', 'Dikonversi ke Piutang'
        VOIDED = 'voided', 'Dibatalkan'

    kp = models.ForeignKey(
        KewajibabPelaksanaan, on_delete=models.CASCADE, related_name='aset_kontrak',
        verbose_name='Kewajiban Pelaksanaan',
    )
    tanggal = models.DateField(verbose_name='Tanggal')
    nilai = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Nilai')
    nilai_tersisa = models.DecimalField(
        max_digits=19, decimal_places=4, verbose_name='Nilai Tersisa',
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE, verbose_name='Status',
    )
    jurnal_header = models.ForeignKey(
        'jurnal.JurnalHeader', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='aset_kontrak_set',
        verbose_name='Jurnal Awal',
    )
    piutang = models.ForeignKey(
        'piutang.PiutangHeader', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='aset_kontrak_sumber',
        verbose_name='Piutang',
    )
    catatan = models.TextField(blank=True, default='', verbose_name='Catatan')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Aset Kontrak'
        verbose_name_plural = 'Aset Kontrak'

    def __str__(self) -> str:
        return f'AsetKontrak KP-{self.kp_id} [{self.nilai}]'
