from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('utang', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='utangheader',
            name='tanggal_jatuh_tempo',
            field=models.DateField(
                blank=True, db_index=True, null=True,
                verbose_name='Tanggal Jatuh Tempo',
            ),
        ),
        migrations.AddField(
            model_name='utangheader',
            name='is_locked',
            field=models.BooleanField(default=False, verbose_name='Terkunci'),
        ),
    ]
