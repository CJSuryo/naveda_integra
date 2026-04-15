"""Replace old sales models (ItemMaster, SalesHeader, SalesDetail) with new models (SalesHeader, SalesItem)."""
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0002_alter_salesheader_options_and_more'),
        ('entitas_bisnis', '0004_entitasbisnislv2_entitasbisnislv3_and_more'),
        ('master_data', '0006_entitasbisnisakun'),
        ('purchase', '0008_subtransactiontype_module_and_more'),
    ]

    operations = [
        # Drop old models
        migrations.DeleteModel(name='SalesDetail'),
        migrations.DeleteModel(name='SalesHeader'),
        migrations.DeleteModel(name='ItemMaster'),

        # Create new SalesHeader
        migrations.CreateModel(
            name='SalesHeader',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('transaction_id', models.CharField(editable=False, max_length=100, unique=True)),
                ('tanggal', models.DateField(db_index=True, default=django.utils.timezone.now, verbose_name='Tanggal')),
                ('deskripsi', models.TextField(blank=True, default='', verbose_name='Deskripsi')),
                ('is_locked', models.BooleanField(default=False, help_text='True jika periode sudah tutup buku.', verbose_name='Locked')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('entitas_bisnis', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='new_sales_headers', to='entitas_bisnis.entitasbisnis', verbose_name='Entitas Bisnis')),
                ('payment_account', models.ForeignKey(help_text='Kas Tunai, Kas di Bank, dll.', on_delete=django.db.models.deletion.PROTECT, related_name='sales_payment_headers', to='master_data.akun', verbose_name='Payment Account')),
            ],
            options={
                'verbose_name': 'Sales Header',
                'verbose_name_plural': 'Sales Headers',
                'ordering': ['-tanggal', '-created_at'],
                'indexes': [
                    models.Index(fields=['tanggal', 'is_locked'], name='idx_nsh_tanggal_locked'),
                    models.Index(fields=['entitas_bisnis', 'tanggal'], name='idx_nsh_eb_tanggal'),
                ],
            },
        ),

        # Create new SalesItem
        migrations.CreateModel(
            name='SalesItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.DecimalField(decimal_places=4, max_digits=15, verbose_name='Quantity')),
                ('selling_price', models.DecimalField(decimal_places=4, max_digits=19, verbose_name='Harga Jual')),
                ('total_sales', models.DecimalField(decimal_places=4, default=0, editable=False, max_digits=19, verbose_name='Total Penjualan')),
                ('cogs_amount', models.DecimalField(decimal_places=4, default=0, help_text='Dihitung otomatis dari FIFO outflow.', max_digits=19, verbose_name='HPP (COGS)')),
                ('tax', models.DecimalField(blank=True, decimal_places=4, max_digits=19, null=True, verbose_name='Tax (Nominal)')),
                ('tax_type', models.CharField(blank=True, choices=[('ppn_keluaran', 'PPN Keluaran'), ('pph_23', 'PPh 23'), ('pph_21', 'PPh 21'), ('pph_4_2', 'PPh 4(2)')], default='', max_length=30, verbose_name='Tax Type')),
                ('tax_payment', models.CharField(blank=True, choices=[('belum_transfer', 'Belum Transfer'), ('sudah_transfer', 'Sudah Transfer')], default='', max_length=20, verbose_name='Tax Payment Status')),
                ('sales_header', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='sales.salesheader')),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='sales_items', to='purchase.itemmasterpurchase')),
                ('sub_transaction_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='sales_items', to='purchase.subtransactiontype', verbose_name='Sub-Transaction Type')),
                ('offset_coa_account', models.ForeignKey(help_text='HPP terkait — auto-fill dari Settings.', on_delete=django.db.models.deletion.PROTECT, related_name='sales_item_offset', to='master_data.akun', verbose_name='Offset CoA (HPP)')),
                ('revenue_account', models.ForeignKey(help_text='Pendapatan terkait item/tipe transaksi.', on_delete=django.db.models.deletion.PROTECT, related_name='sales_item_revenue', to='master_data.akun', verbose_name='Revenue Account')),
                ('inventory_account', models.ForeignKey(blank=True, help_text='Akun persediaan item (dari Item Master CoA).', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='sales_item_inventory', to='master_data.akun', verbose_name='Inventory Account')),
                ('tax_account', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='sales_item_tax', to='master_data.akun', verbose_name='Tax Account')),
                ('tax_payment_account', models.ForeignKey(blank=True, help_text='Utang PPN Keluaran (jika belum transfer).', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='sales_item_tax_payment', to='master_data.akun', verbose_name='Tax Payment Account')),
            ],
            options={
                'verbose_name': 'Sales Item',
                'verbose_name_plural': 'Sales Items',
                'indexes': [
                    models.Index(fields=['sales_header', 'item'], name='idx_nsi_header_item'),
                    models.Index(fields=['item'], name='idx_nsi_item'),
                ],
            },
        ),
    ]
