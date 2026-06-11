from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('piutang', '0008_piutangreklasifikasi_periode_fields'),
    ]
    operations = [
        migrations.AddField(
            model_name='piutangheader',
            name='is_pv_adjusted',
            field=models.BooleanField(default=False, verbose_name='Disesuaikan Nilai Wajar (PV)'),
        ),
        migrations.AddField(
            model_name='piutangheader',
            name='pv_discount_rate',
            field=models.DecimalField(
                blank=True, decimal_places=4, max_digits=8,
                null=True, verbose_name='Market Rate untuk PV (%/tahun)',
            ),
        ),
        migrations.AddField(
            model_name='piutangheader',
            name='nilai_wajar_awal',
            field=models.DecimalField(
                blank=True, decimal_places=4, max_digits=19,
                null=True, verbose_name='Nilai Wajar Awal (PV)',
            ),
        ),
    ]
