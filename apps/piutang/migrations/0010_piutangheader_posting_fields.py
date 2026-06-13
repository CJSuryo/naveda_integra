from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('piutang', '0009_piutangheader_pv_fields'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AlterField(
            model_name='piutangheader',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Draft'),
                    ('pending_approval', 'Menunggu Approval'),
                    ('open', 'Terbuka'),
                    ('partial', 'Sebagian Diterima'),
                    ('paid', 'Lunas'),
                    ('overdue', 'Jatuh Tempo'),
                    ('written_off', 'Dihapusbukukan'),
                    ('cancelled', 'Dibatalkan'),
                ],
                default='draft',
                max_length=20,
                verbose_name='Status',
            ),
        ),
        migrations.AddField(
            model_name='piutangheader',
            name='is_approval_required',
            field=models.BooleanField(default=False, verbose_name='Perlu Approval'),
        ),
        migrations.AddField(
            model_name='piutangheader',
            name='approved_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='piutang_approved',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Disetujui Oleh',
            ),
        ),
        migrations.AddField(
            model_name='piutangheader',
            name='approved_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Disetujui Pada'),
        ),
    ]
