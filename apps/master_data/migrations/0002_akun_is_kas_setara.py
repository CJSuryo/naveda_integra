from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('master_data', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='akun',
            name='is_kas_setara',
            field=models.BooleanField(
                default=False,
                verbose_name='Kas/Setara Kas',
                help_text='Centang jika akun ini kas/bank (dibayar tunai). Biarkan kosong untuk akun piutang/kredit.',
            ),
        ),
    ]
