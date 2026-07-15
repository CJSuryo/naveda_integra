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
                'DROP TABLE IF EXISTS pos_promotions_orderpromotion;',
                'DROP TABLE IF EXISTS pos_promotions_voucher;',
                'DROP TABLE IF EXISTS pos_promotions_campaign;',
                'DROP TABLE IF EXISTS pos_orders_refunditem;',
                'DROP TABLE IF EXISTS pos_orders_refund;',
                'DROP TABLE IF EXISTS pos_orders_orderpayment;',
                'DROP TABLE IF EXISTS pos_orders_orderitemmodifier;',
                'DROP TABLE IF EXISTS pos_orders_orderitem;',
                'DROP TABLE IF EXISTS pos_orders_order;',
                'DROP TABLE IF EXISTS pos_crm_memberpointlog;',
                'DROP TABLE IF EXISTS pos_crm_membertierconfig;',
                'DROP TABLE IF EXISTS pos_crm_member;',
                'DROP TABLE IF EXISTS pos_reports_dailysalessnapshot;',
                "DELETE FROM django_migrations WHERE app IN ('pos_orders', 'pos_crm', 'pos_promotions', 'pos_reports');",
            ],
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
