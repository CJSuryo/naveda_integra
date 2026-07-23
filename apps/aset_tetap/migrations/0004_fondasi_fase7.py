import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('aset_tetap', '0003_asettetaprecord_status_assetdisposal'),
        ('entitas_bisnis', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='asettetaprecord',
            old_name='lokasi',
            new_name='lokasi_legacy',
        ),
        migrations.AlterField(
            model_name='asettetaprecord',
            name='lokasi_legacy',
            field=models.CharField(
                blank=True, max_length=255,
                help_text='Lokasi free-text lama sebelum migrasi ke master Lokasi Aset.',
                verbose_name='Lokasi (Legacy)',
            ),
        ),
        migrations.CreateModel(
            name='LokasiAset',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kode', models.CharField(max_length=50, unique=True, verbose_name='Kode Lokasi')),
                ('nama', models.CharField(max_length=255, verbose_name='Nama Lokasi')),
                ('alamat', models.TextField(blank=True, verbose_name='Alamat')),
                ('is_active', models.BooleanField(default=True, verbose_name='Aktif')),
                ('entitas_bisnis', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                    related_name='lokasi_aset', to='entitas_bisnis.entitasbisnis',
                    verbose_name='Entitas Bisnis',
                )),
            ],
            options={
                'verbose_name': 'Lokasi Aset',
                'verbose_name_plural': 'Lokasi Aset',
                'ordering': ['kode'],
            },
        ),
        migrations.AddField(
            model_name='asettetaprecord',
            name='lokasi_aset',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='aset_records', to='aset_tetap.lokasiaset',
                verbose_name='Lokasi Aset',
            ),
        ),
        migrations.AddField(
            model_name='asettetaprecord',
            name='departemen',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='aset_records', to='entitas_bisnis.entitasbisnislv3',
                verbose_name='Departemen',
            ),
        ),
        migrations.AddField(
            model_name='asettetaprecord',
            name='pic',
            field=models.CharField(blank=True, max_length=255, verbose_name='Penanggung Jawab (PIC)'),
        ),
    ]
