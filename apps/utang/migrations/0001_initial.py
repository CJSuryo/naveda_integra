from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('accounts', '0002_initial'),
        ('entitas_bisnis', '0001_initial'),
        ('jurnal', '0001_initial'),
        ('master_data', '0001_initial'),
        ('purchase', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='UtangHeader',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nomor_utang', models.CharField(editable=False, max_length=100, unique=True, verbose_name='Nomor Utang')),
                ('tanggal', models.DateField(db_index=True, default=django.utils.timezone.now, verbose_name='Tanggal')),
                ('deskripsi', models.CharField(blank=True, default='', max_length=512, verbose_name='Deskripsi')),
                ('total_amount', models.DecimalField(decimal_places=4, default=0, max_digits=19, verbose_name='Total Utang')),
                ('status', models.CharField(choices=[('open', 'Terbuka'), ('partial', 'Sebagian Dibayar'), ('paid', 'Lunas')], default='open', max_length=20, verbose_name='Status')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('entitas_bisnis', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='utang_headers', to='entitas_bisnis.entitasbisnis', verbose_name='Entitas Bisnis')),
                ('purchase_header', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='utang_headers', to='purchase.purchaseheader', verbose_name='Purchase Header')),
            ],
            options={
                'verbose_name': 'Utang Header',
                'verbose_name_plural': 'Utang Header',
                'ordering': ['-tanggal', '-created_at'],
                'indexes': [models.Index(fields=['tanggal', 'status'], name='idx_utang_tanggal_status')],
            },
        ),
        migrations.CreateModel(
            name='UtangDetail',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.CharField(blank=True, default='', max_length=255, verbose_name='Keterangan')),
                ('amount', models.DecimalField(decimal_places=4, max_digits=19, verbose_name='Jumlah Utang')),
                ('coa_utang_account', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='utang_details', to='master_data.akun', verbose_name='Akun Utang')),
                ('purchase_item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='utang_details', to='purchase.purchaseitem', verbose_name='Purchase Item')),
                ('utang_header', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='details', to='utang.utangheader', verbose_name='Utang Header')),
            ],
            options={
                'verbose_name': 'Utang Detail',
                'verbose_name_plural': 'Utang Detail',
                'indexes': [models.Index(fields=['utang_header', 'coa_utang_account'], name='idx_ud_header_coa')],
            },
        ),
        migrations.CreateModel(
            name='UtangTerhapus',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nomor_utang', models.CharField(max_length=100, verbose_name='Nomor Utang')),
                ('uraian', models.CharField(blank=True, default='', max_length=512, verbose_name='Uraian')),
                ('entitas_bisnis_nama', models.CharField(blank=True, max_length=255, verbose_name='Entitas Bisnis')),
                ('tanggal', models.DateField(blank=True, null=True, verbose_name='Tanggal Utang')),
                ('deleted_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Dihapus Pada')),
                ('snapshot', models.JSONField(default=dict, verbose_name='Snapshot Utang')),
                ('deleted_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='utang_terhapus', to='accounts.user', verbose_name='Dihapus Oleh')),
            ],
            options={
                'verbose_name': 'Utang Terhapus',
                'verbose_name_plural': 'Utang Terhapus',
                'ordering': ['-deleted_at'],
                'indexes': [models.Index(fields=['deleted_at'], name='idx_utang_terhapus_deleted')],
            },
        ),
        migrations.CreateModel(
            name='UtangPembayaran',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tanggal', models.DateField(db_index=True, default=django.utils.timezone.now, verbose_name='Tanggal Pembayaran')),
                ('jumlah', models.DecimalField(decimal_places=4, max_digits=19, verbose_name='Jumlah Pembayaran')),
                ('keterangan', models.CharField(blank=True, default='', max_length=512, verbose_name='Keterangan')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('coa_account', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='utang_payments', to='master_data.akun', verbose_name='Akun Pembayaran')),
                ('jurnal_header', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='utang_payments', to='jurnal.jurnalheader', verbose_name='Jurnal Pembayaran')),
                ('utang_detail', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='payments', to='utang.utangdetail', verbose_name='Utang Detail')),
                ('utang_header', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pembayaran', to='utang.utangheader', verbose_name='Utang Header')),
            ],
            options={
                'verbose_name': 'Utang Pembayaran',
                'verbose_name_plural': 'Utang Pembayaran',
                'ordering': ['-tanggal', '-created_at'],
                'indexes': [models.Index(fields=['utang_header', 'tanggal'], name='idx_up_header_tanggal')],
            },
        ),
    ]
