import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('master_data', '0001_initial'),
        ('piutang', '0013_piutang_lancar_accounts'),
    ]

    operations = [
        migrations.AddField(
            model_name='piutangheader',
            name='penyisihan_allowance_account',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='piutang_psh_allowance',
                to='master_data.akun',
                verbose_name='Akun Cadangan Kerugian Piutang (Penyisihan)',
            ),
        ),
        migrations.AddField(
            model_name='piutangheader',
            name='penyisihan_expense_account',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='piutang_psh_expense',
                to='master_data.akun',
                verbose_name='Akun Beban Penyisihan',
            ),
        ),
    ]
