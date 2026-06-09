# Generated manually — expand RecurringTemplate from placeholder to full model

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('entitas_bisnis', '0002_is_company_profile'),
        ('master_data', '0001_initial'),
        ('pendapatan', '0002_deferred_revenue_models'),
        ('purchase', '0006_add_pendapatan_module_choice'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ForeignKey: entitas_bisnis (non-nullable — use default=1, preserve_default=False)
        migrations.AddField(
            model_name='recurringtemplate',
            name='entitas_bisnis',
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.PROTECT,
                to='entitas_bisnis.entitasbisnis',
                verbose_name='Entitas Bisnis',
            ),
            preserve_default=False,
        ),
        # ForeignKey: entitas_bisnis_lv2 (nullable)
        migrations.AddField(
            model_name='recurringtemplate',
            name='entitas_bisnis_lv2',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='entitas_bisnis.entitasbisnislv2',
                verbose_name='Entitas Bisnis Lv2',
            ),
        ),
        # ForeignKey: entitas_bisnis_lv3 (nullable)
        migrations.AddField(
            model_name='recurringtemplate',
            name='entitas_bisnis_lv3',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='entitas_bisnis.entitasbisnislv3',
                verbose_name='Entitas Bisnis Lv3',
            ),
        ),
        # ForeignKey: sub_transaction_type (non-nullable)
        migrations.AddField(
            model_name='recurringtemplate',
            name='sub_transaction_type',
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.PROTECT,
                to='purchase.subtransactiontype',
                verbose_name='Sub Transaction Type',
            ),
            preserve_default=False,
        ),
        # ForeignKey: revenue_account (non-nullable)
        migrations.AddField(
            model_name='recurringtemplate',
            name='revenue_account',
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='recurring_revenue_templates',
                to='master_data.akun',
                verbose_name='Akun Pendapatan',
            ),
            preserve_default=False,
        ),
        # ForeignKey: payment_account (nullable)
        migrations.AddField(
            model_name='recurringtemplate',
            name='payment_account',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='recurring_payment_templates',
                to='master_data.akun',
                verbose_name='Akun Pembayaran',
            ),
        ),
        # ForeignKey: created_by (nullable)
        migrations.AddField(
            model_name='recurringtemplate',
            name='created_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to=settings.AUTH_USER_MODEL,
                verbose_name='Dibuat Oleh',
            ),
        ),
        # Simple fields
        migrations.AddField(
            model_name='recurringtemplate',
            name='deskripsi_item',
            field=models.TextField(default='', verbose_name='Deskripsi Item'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='recurringtemplate',
            name='kategori',
            field=models.CharField(
                choices=[
                    ('sewa', 'Sewa'),
                    ('jasa', 'Jasa'),
                    ('bunga', 'Bunga'),
                    ('dividen', 'Dividen'),
                    ('komisi', 'Komisi'),
                    ('royalti', 'Royalti'),
                    ('management_fee', 'Management Fee'),
                    ('penjualan_aset', 'Penjualan Aset'),
                    ('lainnya', 'Lainnya'),
                ],
                default='lainnya',
                max_length=30,
                verbose_name='Kategori',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='recurringtemplate',
            name='jumlah',
            field=models.DecimalField(
                decimal_places=4,
                default=0,
                max_digits=19,
                verbose_name='Jumlah per Periode',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='recurringtemplate',
            name='payment_type',
            field=models.CharField(
                choices=[('cash', 'Cash'), ('credit', 'Kredit')],
                default='cash',
                max_length=10,
                verbose_name='Tipe Pembayaran',
            ),
        ),
        migrations.AddField(
            model_name='recurringtemplate',
            name='frekuensi',
            field=models.CharField(
                choices=[
                    ('harian', 'Harian'),
                    ('mingguan', 'Mingguan'),
                    ('bulanan', 'Bulanan'),
                    ('triwulanan', 'Triwulanan'),
                    ('semesteran', 'Semesteran'),
                    ('tahunan', 'Tahunan'),
                ],
                default='bulanan',
                max_length=20,
                verbose_name='Frekuensi',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='recurringtemplate',
            name='tanggal_mulai',
            field=models.DateField(
                default=django.utils.timezone.now,
                verbose_name='Tanggal Mulai',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='recurringtemplate',
            name='tanggal_selesai',
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name='Tanggal Selesai',
            ),
        ),
        migrations.AddField(
            model_name='recurringtemplate',
            name='tanggal_berikutnya',
            field=models.DateField(
                default=django.utils.timezone.now,
                verbose_name='Tanggal Berikutnya',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='recurringtemplate',
            name='auto_confirm',
            field=models.BooleanField(default=False, verbose_name='Auto Konfirmasi'),
        ),
        migrations.AddField(
            model_name='recurringtemplate',
            name='is_active',
            field=models.BooleanField(default=True, verbose_name='Aktif'),
        ),
        migrations.AddField(
            model_name='recurringtemplate',
            name='created_at',
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
        # Update Meta options
        migrations.AlterModelOptions(
            name='recurringtemplate',
            options={
                'ordering': ['tanggal_berikutnya'],
                'verbose_name': 'Recurring Template',
                'verbose_name_plural': 'Recurring Templates',
            },
        ),
        # Update nama field verbose_name
        migrations.AlterField(
            model_name='recurringtemplate',
            name='nama',
            field=models.CharField(max_length=255, verbose_name='Nama Template'),
        ),
    ]
