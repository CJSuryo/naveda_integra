"""Transition sales schema from single-EB (SalesHeader.entitas_bisnis) to
multi-EB groups (SalesEntitasBisnis) pattern, matching the purchase module."""

import django.db.models.deletion
from django.db import migrations, models


def create_sales_eb_from_headers(apps, schema_editor):
    """Create a SalesEntitasBisnis record for each existing SalesHeader."""
    SalesHeader = apps.get_model('sales', 'SalesHeader')
    SalesEntitasBisnis = apps.get_model('sales', 'SalesEntitasBisnis')

    for header in SalesHeader.objects.all():
        SalesEntitasBisnis.objects.create(
            sales_header=header,
            entitas_bisnis_id=header.entitas_bisnis_id,
            entitas_bisnis_lv2_id=None,
            entitas_bisnis_lv3_id=None,
            payment_account_id=header.payment_account_id,
        )


def set_sales_item_eb(apps, schema_editor):
    """Point each SalesItem.sales_eb to the EB group created for its header."""
    SalesItem = apps.get_model('sales', 'SalesItem')
    SalesEntitasBisnis = apps.get_model('sales', 'SalesEntitasBisnis')

    eb_by_header = {seb.sales_header_id: seb for seb in SalesEntitasBisnis.objects.all()}
    items_to_update = []
    for item in SalesItem.objects.all():
        item.sales_eb = eb_by_header[item.sales_header_id]
        items_to_update.append(item)
    if items_to_update:
        SalesItem.objects.bulk_update(items_to_update, ['sales_eb'])


class Migration(migrations.Migration):

    dependencies = [
        ('entitas_bisnis', '0001_initial'),
        ('master_data', '0001_initial'),
        ('sales', '0001_initial'),
    ]

    operations = [
        # ── 1. Drop indexes that reference fields about to be removed ──────────
        migrations.RemoveIndex(model_name='salesheader', name='idx_nsh_eb_tanggal'),
        migrations.RemoveIndex(model_name='salesitem', name='idx_nsi_header_item'),

        # ── 2. Create SalesEntitasBisnis model ────────────────────────────────
        migrations.CreateModel(
            name='SalesEntitasBisnis',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sales_header', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='entitas_groups',
                    to='sales.salesheader',
                )),
                ('entitas_bisnis', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='sales_groups',
                    to='entitas_bisnis.entitasbisnis',
                    verbose_name='Entitas Bisnis (Lv1)',
                )),
                ('entitas_bisnis_lv2', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='sales_groups',
                    to='entitas_bisnis.entitasbisnislv2',
                    verbose_name='Entitas Bisnis Lv2',
                )),
                ('entitas_bisnis_lv3', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='sales_groups',
                    to='entitas_bisnis.entitasbisnislv3',
                    verbose_name='Entitas Bisnis Lv3',
                )),
                ('payment_account', models.ForeignKey(
                    help_text='Kas Tunai, Kas di Bank, dll.',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='sales_eb_payment',
                    to='master_data.akun',
                    verbose_name='Payment Account',
                )),
            ],
            options={
                'verbose_name': 'Sales Entitas Bisnis',
                'verbose_name_plural': 'Sales Entitas Bisnis',
            },
        ),

        # ── 3. Data migration: populate SalesEntitasBisnis from SalesHeader ───
        migrations.RunPython(create_sales_eb_from_headers, migrations.RunPython.noop),

        # ── 4. Add nullable sales_eb FK to SalesItem ──────────────────────────
        migrations.AddField(
            model_name='salesitem',
            name='sales_eb',
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='items',
                to='sales.salesentitasbisnis',
            ),
        ),

        # ── 5. Data migration: set sales_eb on each SalesItem ─────────────────
        migrations.RunPython(set_sales_item_eb, migrations.RunPython.noop),

        # ── 6. Make sales_eb NOT NULL ─────────────────────────────────────────
        migrations.AlterField(
            model_name='salesitem',
            name='sales_eb',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='items',
                to='sales.salesentitasbisnis',
            ),
        ),

        # ── 7. Remove old FK from SalesItem ───────────────────────────────────
        migrations.RemoveField(model_name='salesitem', name='sales_header'),

        # ── 8. Remove old FKs from SalesHeader ────────────────────────────────
        migrations.RemoveField(model_name='salesheader', name='entitas_bisnis'),
        migrations.RemoveField(model_name='salesheader', name='payment_account'),

        # ── 9. Add indexes ─────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name='salesentitasbisnis',
            index=models.Index(fields=['sales_header', 'entitas_bisnis'], name='idx_seb_header_eb'),
        ),
        migrations.AddIndex(
            model_name='salesentitasbisnis',
            index=models.Index(fields=['entitas_bisnis_lv2'], name='idx_seb_lv2'),
        ),
        migrations.AddIndex(
            model_name='salesentitasbisnis',
            index=models.Index(fields=['entitas_bisnis_lv3'], name='idx_seb_lv3'),
        ),
        migrations.AddIndex(
            model_name='salesitem',
            index=models.Index(fields=['sales_eb', 'item'], name='idx_nsi_eb_item'),
        ),
    ]
