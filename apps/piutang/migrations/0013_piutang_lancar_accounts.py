import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('master_data', '0001_initial'),
        ('piutang', '0012_interest_income_account'),
    ]

    operations = [
        # PiutangHeader — two new reklasifikasi account fields
        migrations.AddField(
            model_name='piutangheader',
            name='coa_piutang_lancar_account',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='piutang_lancar_headers',
                to='master_data.akun',
                verbose_name='Akun Piutang Bagian Lancar',
            ),
        ),
        migrations.AddField(
            model_name='piutangheader',
            name='deferred_income_lancar_account',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='piutang_deferred_income_lancar',
                to='master_data.akun',
                verbose_name='Akun Pend. Bunga Ditangguhkan Bagian Lancar',
            ),
        ),
        # PiutangReklasifikasi — track deferred-income portion of each reklasifikasi
        migrations.AddField(
            model_name='piutangreklasifikasi',
            name='jumlah_deferred',
            field=models.DecimalField(
                blank=True, null=True,
                decimal_places=4, max_digits=19,
                verbose_name='Jumlah Diskonto Direklasifikasi',
            ),
        ),
        migrations.AddField(
            model_name='piutangreklasifikasi',
            name='dari_akun_deferred',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='piutang_rkl_deferred_dari',
                to='master_data.akun',
                verbose_name='Dari Akun Diskonto (LT)',
            ),
        ),
        migrations.AddField(
            model_name='piutangreklasifikasi',
            name='ke_akun_deferred',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='piutang_rkl_deferred_ke',
                to='master_data.akun',
                verbose_name='Ke Akun Diskonto (BL)',
            ),
        ),
    ]
