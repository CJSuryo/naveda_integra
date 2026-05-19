from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('purchase', '0004_subtransactiontype_default_inventory_account_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='subtransactiontype',
            name='payment_term_days',
            field=models.PositiveIntegerField(
                blank=True, null=True,
                verbose_name='Payment Term (hari)',
                help_text='Otomatis isi tanggal jatuh tempo utang. Kosongkan jika tidak ada.',
            ),
        ),
    ]
