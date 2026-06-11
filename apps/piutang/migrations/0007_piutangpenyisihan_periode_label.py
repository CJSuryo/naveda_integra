from django.db import migrations, models


def backfill_periode_label(apps, schema_editor):
    PiutangPenyisihan = apps.get_model('piutang', 'PiutangPenyisihan')
    for entry in PiutangPenyisihan.objects.filter(jenis='batch'):
        entry.periode_label = entry.tanggal.strftime('%Y-%m')
        entry.save(update_fields=['periode_label'])


class Migration(migrations.Migration):
    dependencies = [
        ('piutang', '0006_seed_penyisihan_rates'),
    ]
    operations = [
        migrations.AddField(
            model_name='piutangpenyisihan',
            name='periode_label',
            field=models.CharField(
                blank=True, db_index=True, default='', max_length=20,
                verbose_name='Periode',
                help_text='YYYY-MM — diisi otomatis untuk jenis batch',
            ),
        ),
        migrations.RunPython(backfill_periode_label, migrations.RunPython.noop),
    ]
