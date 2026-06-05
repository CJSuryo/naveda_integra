from decimal import Decimal


def resolve_pos_config(lv3) -> dict:
    """Return effective POS config for a lv3 outlet.

    Resolution order: lv3 (OutletPOSConfig) → lv2 (StorePOSConfig) → lv1 (MerchantPOSConfig).
    lv2 (StorePOSConfig) overrides tax only; STT + accounts cascade lv3 → lv1 directly.
    """
    outlet = getattr(lv3, 'pos_config', None)
    store = getattr(getattr(lv3, 'parent_lv2', None), 'pos_config', None)
    merchant = getattr(
        getattr(getattr(lv3, 'parent_lv2', None), 'entitas_bisnis', None),
        'pos_config',
        None,
    )

    def first(*vals):
        return next((v for v in vals if v is not None), None)

    tax = first(
        outlet.tax_pct if outlet else None,
        store.tax_pct if store else None,
        merchant.default_tax_pct if merchant else None,
    )

    return {
        'sub_transaction_type_id': first(
            outlet.sub_transaction_type_id if outlet else None,
            merchant.sub_transaction_type_id if merchant else None,
        ),
        'revenue_account_id': first(
            outlet.revenue_account_id if outlet else None,
            merchant.revenue_account_id if merchant else None,
        ),
        'offset_coa_account_id': first(
            outlet.offset_coa_account_id if outlet else None,
            merchant.offset_coa_account_id if merchant else None,
        ),
        'payment_account_id': first(
            outlet.default_payment_account_id if outlet else None,
            merchant.default_payment_account_id if merchant else None,
        ),
        'tax_pct': tax if tax is not None else Decimal('0'),
        'sub_transaction_type': first(
            outlet.sub_transaction_type_id if outlet else None,
            merchant.sub_transaction_type_id if merchant else None,
        ),
        'qris_image_url': (
            merchant.qris_image.url
            if merchant and merchant.qris_image
            else None
        ),
    }
