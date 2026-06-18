import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pendapatan', '0004_recurring_template_updated_at'),
        ('master_data', '0001_initial'),
        ('jurnal', '0003_add_jurnal_terhapus_and_persentase'),
        ('piutang', '0016_psak71_mode_ecl_staging'),
    ]

    operations = [
        # 1. Rename model PendapatanItem → KewajibabPelaksanaan
        #    This also renames the DB table:
        #    pendapatan_pendapatanitem → pendapatan_kewajibabpelaksanaan
        migrations.RenameModel(
            old_name='PendapatanItem',
            new_name='KewajibabPelaksanaan',
        ),
        # 2. Rename field jumlah_bruto → nilai_kontrak
        migrations.RenameField(
            model_name='kewajibabpelaksanaan',
            old_name='jumlah_bruto',
            new_name='nilai_kontrak',
        ),
        # 3. Add standar_akuntansi to PendapatanHeader
        migrations.AddField(
            model_name='pendapatanheader',
            name='standar_akuntansi',
            field=models.CharField(
                choices=[('PSAK_71_72', 'PSAK 71/72'), ('SAK_ETAP', 'SAK ETAP')],
                default='PSAK_71_72',
                max_length=20,
                verbose_name='Standar Akuntansi',
            ),
        ),
        # 4. Add PSAK 72 fields to KewajibabPelaksanaan
        migrations.AddField(
            model_name='kewajibabpelaksanaan',
            name='harga_j',
            field=models.DecimalField(
                decimal_places=4,
                default=0,
                max_digits=19,
                verbose_name='Harga Alokasi (PSAK 72)',
            ),
        ),
        migrations.AddField(
            model_name='kewajibabpelaksanaan',
            name='recognition_type',
            field=models.CharField(
                choices=[('point_in_time', 'Point-in-Time'), ('over_time', 'Over Time')],
                default='point_in_time',
                max_length=20,
                verbose_name='Tipe Pengakuan',
            ),
        ),
        migrations.AddField(
            model_name='kewajibabpelaksanaan',
            name='ot_tipe_aliran',
            field=models.CharField(blank=True, default='', max_length=30, verbose_name='Tipe Aliran'),
        ),
        migrations.AddField(
            model_name='kewajibabpelaksanaan',
            name='ot_progress_method',
            field=models.CharField(blank=True, default='', max_length=30, verbose_name='Metode Progress'),
        ),
        migrations.AddField(
            model_name='kewajibabpelaksanaan',
            name='ot_tanggal_mulai',
            field=models.DateField(blank=True, null=True, verbose_name='Tanggal Mulai OT'),
        ),
        migrations.AddField(
            model_name='kewajibabpelaksanaan',
            name='ot_tanggal_selesai',
            field=models.DateField(blank=True, null=True, verbose_name='Tanggal Selesai OT'),
        ),
        migrations.AddField(
            model_name='kewajibabpelaksanaan',
            name='ot_liabilitas_kontrak_acct',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='+',
                to='master_data.akun',
                verbose_name='Akun Liabilitas Kontrak',
            ),
        ),
        migrations.AddField(
            model_name='kewajibabpelaksanaan',
            name='ot_aset_kontrak_acct',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='+',
                to='master_data.akun',
                verbose_name='Akun Aset Kontrak',
            ),
        ),
        migrations.AddField(
            model_name='kewajibabpelaksanaan',
            name='ot_biaya_estimasi_total',
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                max_digits=19,
                null=True,
                verbose_name='Biaya Estimasi Total',
            ),
        ),
        # 5. Create JadwalPengakuan
        migrations.CreateModel(
            name='JadwalPengakuan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipe_aliran', models.CharField(
                    choices=[
                        ('advance_payment_cash', 'Advance Payment (Cash)'),
                        ('periodic_billing', 'Periodic Billing'),
                        ('performance_first', 'Performance First'),
                    ],
                    max_length=30,
                    verbose_name='Tipe Aliran',
                )),
                ('progress_method', models.CharField(
                    choices=[
                        ('straight_line', 'Garis Lurus'),
                        ('percentage_completion', 'Persentase Selesai'),
                        ('milestone', 'Milestone'),
                    ],
                    max_length=30,
                    verbose_name='Metode Progress',
                )),
                ('tanggal_mulai', models.DateField(verbose_name='Tanggal Mulai')),
                ('tanggal_selesai', models.DateField(verbose_name='Tanggal Selesai')),
                ('biaya_estimasi_total', models.DecimalField(
                    blank=True,
                    decimal_places=4,
                    max_digits=19,
                    null=True,
                    verbose_name='Biaya Estimasi Total',
                )),
                ('nilai_total', models.DecimalField(decimal_places=4, max_digits=19, verbose_name='Nilai Total')),
                ('nilai_diakui', models.DecimalField(
                    decimal_places=4,
                    default=0,
                    max_digits=19,
                    verbose_name='Nilai Diakui',
                )),
                ('status', models.CharField(
                    choices=[
                        ('active', 'Aktif'),
                        ('completed', 'Selesai'),
                        ('voided', 'Dibatalkan'),
                    ],
                    default='active',
                    max_length=20,
                    verbose_name='Status',
                )),
                ('kp', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='jadwal',
                    to='pendapatan.kewajibabpelaksanaan',
                    verbose_name='Kewajiban Pelaksanaan',
                )),
                ('liabilitas_kontrak_acct', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='+',
                    to='master_data.akun',
                    verbose_name='Akun Liabilitas Kontrak',
                )),
                ('aset_kontrak_acct', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='+',
                    to='master_data.akun',
                    verbose_name='Akun Aset Kontrak',
                )),
            ],
            options={
                'verbose_name': 'Jadwal Pengakuan',
                'verbose_name_plural': 'Jadwal Pengakuan',
            },
        ),
        # 6. Create EntriPengakuan
        migrations.CreateModel(
            name='EntriPengakuan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tanggal_target', models.DateField(verbose_name='Tanggal Target')),
                ('nilai', models.DecimalField(decimal_places=4, max_digits=19, verbose_name='Nilai')),
                ('nilai_diakui', models.DecimalField(
                    decimal_places=4,
                    default=0,
                    max_digits=19,
                    verbose_name='Nilai Diakui',
                )),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Belum Diakui'),
                        ('recognized', 'Sudah Diakui'),
                        ('skipped', 'Dilewati'),
                    ],
                    default='pending',
                    max_length=20,
                    verbose_name='Status',
                )),
                ('catatan', models.TextField(blank=True, default='', verbose_name='Catatan')),
                ('jadwal', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='entri',
                    to='pendapatan.jadwalpengakuan',
                    verbose_name='Jadwal Pengakuan',
                )),
                ('jurnal_header', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='entri_pengakuan',
                    to='jurnal.jurnalheader',
                    verbose_name='Jurnal',
                )),
            ],
            options={
                'verbose_name': 'Entri Pengakuan',
                'verbose_name_plural': 'Entri Pengakuan',
                'ordering': ['tanggal_target'],
            },
        ),
        # 7. Create AsetKontrak
        migrations.CreateModel(
            name='AsetKontrak',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tanggal', models.DateField(verbose_name='Tanggal')),
                ('nilai', models.DecimalField(decimal_places=4, max_digits=19, verbose_name='Nilai')),
                ('nilai_tersisa', models.DecimalField(decimal_places=4, max_digits=19, verbose_name='Nilai Tersisa')),
                ('status', models.CharField(
                    choices=[
                        ('active', 'Aktif'),
                        ('converted', 'Dikonversi ke Piutang'),
                        ('voided', 'Dibatalkan'),
                    ],
                    default='active',
                    max_length=20,
                    verbose_name='Status',
                )),
                ('catatan', models.TextField(blank=True, default='', verbose_name='Catatan')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('kp', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='aset_kontrak',
                    to='pendapatan.kewajibabpelaksanaan',
                    verbose_name='Kewajiban Pelaksanaan',
                )),
                ('jurnal_header', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='aset_kontrak_set',
                    to='jurnal.jurnalheader',
                    verbose_name='Jurnal Awal',
                )),
                ('piutang', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='aset_kontrak_sumber',
                    to='piutang.piutangheader',
                    verbose_name='Piutang',
                )),
            ],
            options={
                'verbose_name': 'Aset Kontrak',
                'verbose_name_plural': 'Aset Kontrak',
            },
        ),
    ]
