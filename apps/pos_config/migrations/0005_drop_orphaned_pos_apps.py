from django.db import migrations


class Migration(migrations.Migration):
    """Drop tables left behind by the pos_orders/pos_crm/pos_promotions/pos_reports
    apps removed in commit 251470f. Those apps were unwired from INSTALLED_APPS
    without dropping their tables; this finishes the cleanup now that the data
    is confirmed unused.
    """

    dependencies = [
        ('pos_config', '0004_outlet_config_qris_image'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                'DROP TABLE IF EXISTS pos_promotions_orderpromotion CASCADE;',
                'DROP TABLE IF EXISTS pos_promotions_voucher CASCADE;',
                'DROP TABLE IF EXISTS pos_promotions_campaign CASCADE;',
                'DROP TABLE IF EXISTS pos_orders_refunditem CASCADE;',
                'DROP TABLE IF EXISTS pos_orders_refund CASCADE;',
                'DROP TABLE IF EXISTS pos_orders_orderpayment CASCADE;',
                'DROP TABLE IF EXISTS pos_orders_orderitemmodifier CASCADE;',
                'DROP TABLE IF EXISTS pos_orders_orderitem CASCADE;',
                'DROP TABLE IF EXISTS pos_orders_order CASCADE;',
                'DROP TABLE IF EXISTS pos_crm_memberpointlog CASCADE;',
                'DROP TABLE IF EXISTS pos_crm_membertierconfig CASCADE;',
                'DROP TABLE IF EXISTS pos_crm_member CASCADE;',
                'DROP TABLE IF EXISTS pos_reports_dailysalessnapshot CASCADE;',
                "DELETE FROM django_migrations WHERE app IN ('pos_orders', 'pos_crm', 'pos_promotions', 'pos_reports');",
            ],
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
