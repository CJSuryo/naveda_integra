"""
Migration 0002 — Ekuitas redesign

Changes:
- Add Pemilik model
- Add ModalDisetor.pemilik FK (nullable → populated from nama_pemilik → made non-nullable)
- Remove ModalDisetor.nama_pemilik and ModalDisetor.persentase_kepemilikan
- Add ModalDisetor.jurnal_header FK (nullable)
- Add ModalDisetorDebit model
"""
import django.db.models.deletion
from django.db import migrations, models


def port_pemilik_forward(apps, schema_editor):
    """Create Pemilik from unique nama_pemilik values and link ModalDisetor rows."""
    ModalDisetor = apps.get_model('ekuitas', 'ModalDisetor')
    Pemilik = apps.get_model('ekuitas', 'Pemilik')
    for record in ModalDisetor.objects.all():
        nama = (record.nama_pemilik or '').strip() or 'Tidak Diketahui'
        pemilik, _ = Pemilik.objects.get_or_create(nama=nama)
        record.pemilik = pemilik
        record.save(update_fields=['pemilik'])


def port_pemilik_reverse(apps, schema_editor):
    """Restore nama_pemilik from pemilik.nama."""
    ModalDisetor = apps.get_model('ekuitas', 'ModalDisetor')
    for record in ModalDisetor.objects.select_related('pemilik').all():
        if record.pemilik:
            record.nama_pemilik = record.pemilik.nama
            record.save(update_fields=['nama_pemilik'])


class Migration(migrations.Migration):

    dependencies = [
        ('ekuitas', '0001_initial'),
        ('jurnal', '0001_initial'),
    ]

    operations = [
        # 1. Create Pemilik
        migrations.CreateModel(
            name='Pemilik',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nama', models.CharField(max_length=255, unique=True, verbose_name='Nama Pemilik')),
                ('keterangan', models.TextField(blank=True, verbose_name='Keterangan')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Pemilik',
                'verbose_name_plural': 'Pemilik',
                'ordering': ['nama'],
            },
        ),

        # 2. Add pemilik as nullable FK (so existing rows don't need a default)
        migrations.AddField(
            model_name='modaldisetor',
            name='pemilik',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='modal_disetors',
                to='ekuitas.pemilik',
                verbose_name='Pemilik',
            ),
        ),

        # 3. Data migration: populate pemilik from nama_pemilik
        migrations.RunPython(port_pemilik_forward, reverse_code=port_pemilik_reverse),

        # 4. Make pemilik non-nullable
        migrations.AlterField(
            model_name='modaldisetor',
            name='pemilik',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='modal_disetors',
                to='ekuitas.pemilik',
                verbose_name='Pemilik',
            ),
        ),

        # 5. Remove old fields
        migrations.RemoveField(model_name='modaldisetor', name='nama_pemilik'),
        migrations.RemoveField(model_name='modaldisetor', name='persentase_kepemilikan'),

        # 6. Add jurnal_header FK (nullable)
        migrations.AddField(
            model_name='modaldisetor',
            name='jurnal_header',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='modal_disetors',
                to='jurnal.jurnalheader',
                verbose_name='Jurnal',
            ),
        ),

        # 7. Create ModalDisetorDebit
        migrations.CreateModel(
            name='ModalDisetorDebit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('jumlah', models.DecimalField(decimal_places=4, max_digits=19, verbose_name='Jumlah Debit')),
                ('modal_disetor', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='debit_lines',
                    to='ekuitas.modaldisetor',
                    verbose_name='Modal Disetor',
                )),
                ('akun', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    to='master_data.akun',
                    verbose_name='Akun',
                )),
            ],
            options={
                'verbose_name': 'Baris Debit Modal Disetor',
                'verbose_name_plural': 'Baris Debit Modal Disetor',
            },
        ),
    ]
