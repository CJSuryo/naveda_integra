from django.db import migrations, models
import django.db.models.deletion


def migrate_tax_data(apps, schema_editor):
    """Copy existing single-tax KP data into KPTaxLine records before removing old columns."""
    KPTaxLine = apps.get_model('pendapatan', 'KPTaxLine')
    KewajibabPelaksanaan = apps.get_model('pendapatan', 'KewajibabPelaksanaan')
    for kp in KewajibabPelaksanaan.objects.exclude(tax_type='').filter(
        tax_account__isnull=False,
        tax_payment_account__isnull=False,
    ):
        KPTaxLine.objects.create(
            kp=kp,
            tax_type=kp.tax_type,
            tax=kp.tax,
            tax_account_id=kp.tax_account_id,
            tax_payment_account_id=kp.tax_payment_account_id,
        )


def reverse_migrate_tax_data(apps, schema_editor):
    KPTaxLine = apps.get_model('pendapatan', 'KPTaxLine')
    KewajibabPelaksanaan = apps.get_model('pendapatan', 'KewajibabPelaksanaan')
    for tl in KPTaxLine.objects.select_related('kp').all():
        kp = tl.kp
        kp.tax_type = tl.tax_type
        kp.tax = tl.tax
        kp.tax_account_id = tl.tax_account_id
        kp.tax_payment_account_id = tl.tax_payment_account_id
        kp.save(update_fields=['tax_type', 'tax', 'tax_account_id', 'tax_payment_account_id'])


class Migration(migrations.Migration):
    dependencies = [
        ('pendapatan', '0007_psak72_cleanup'),
    ]

    operations = [
        migrations.CreateModel(
            name='KPTaxLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tax_type', models.CharField(
                    choices=[('ppn_keluaran', 'PPN Keluaran'), ('pph_23', 'PPh 23'), ('pph_21', 'PPh 21'), ('pph_4_2', 'PPh 4(2)')],
                    max_length=30, verbose_name='Tipe Pajak'
                )),
                ('tax', models.DecimalField(blank=True, decimal_places=4, help_text='Jika diisi, nilai ini menggantikan perhitungan tarif otomatis.', max_digits=19, null=True, verbose_name='Pajak (Override Manual)')),
                ('kp', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='tax_lines',
                    to='pendapatan.kewajibabpelaksanaan',
                    verbose_name='Kewajiban Pelaksanaan',
                )),
                ('tax_account', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='kp_tax_lines_pajak',
                    to='master_data.akun',
                    verbose_name='Akun Pajak',
                )),
                ('tax_payment_account', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='kp_tax_lines_lawan',
                    to='master_data.akun',
                    verbose_name='Akun Lawan Pajak',
                )),
            ],
            options={'verbose_name': 'KP Tax Line', 'verbose_name_plural': 'KP Tax Lines', 'ordering': ['id']},
        ),
        migrations.RunPython(migrate_tax_data, reverse_code=reverse_migrate_tax_data),
        migrations.RemoveField(model_name='kewajibabpelaksanaan', name='tax'),
        migrations.RemoveField(model_name='kewajibabpelaksanaan', name='tax_type'),
        migrations.RemoveField(model_name='kewajibabpelaksanaan', name='tax_account'),
        migrations.RemoveField(model_name='kewajibabpelaksanaan', name='tax_payment'),
        migrations.RemoveField(model_name='kewajibabpelaksanaan', name='tax_payment_account'),
    ]
