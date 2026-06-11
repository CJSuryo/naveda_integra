from django.db import migrations, models


def populate_periode_fields(apps, schema_editor):
    PiutangReklasifikasi = apps.get_model('piutang', 'PiutangReklasifikasi')
    for rkl in PiutangReklasifikasi.objects.all():
        rkl.periode_bulan = rkl.tanggal.month
        rkl.periode_tahun = rkl.tanggal.year
        rkl.save(update_fields=['periode_bulan', 'periode_tahun'])


class Migration(migrations.Migration):
    dependencies = [
        ('piutang', '0007_piutangpenyisihan_periode_label'),
    ]
    operations = [
        migrations.AddField(
            model_name='piutangreklasifikasi',
            name='periode_bulan',
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Periode Bulan'),
        ),
        migrations.AddField(
            model_name='piutangreklasifikasi',
            name='periode_tahun',
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Periode Tahun'),
        ),
        migrations.RunPython(populate_periode_fields, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='piutangreklasifikasi',
            constraint=models.UniqueConstraint(
                condition=models.Q(periode_bulan__isnull=False, periode_tahun__isnull=False),
                fields=['piutang_header', 'periode_bulan', 'periode_tahun'],
                name='uniq_rkl_header_periode',
            ),
        ),
    ]
