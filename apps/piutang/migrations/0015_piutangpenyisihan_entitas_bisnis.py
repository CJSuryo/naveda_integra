import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('entitas_bisnis', '0001_initial'),
        ('piutang', '0014_piutang_penyisihan_accounts'),
    ]

    operations = [
        migrations.AddField(
            model_name='piutangpenyisihan',
            name='entitas_bisnis',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='piutang_penyisihan_entries',
                to='entitas_bisnis.entitasbisnis',
                verbose_name='Entitas Bisnis',
            ),
        ),
    ]
