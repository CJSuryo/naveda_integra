from decimal import Decimal


def resolve_pos_config(lv3) -> dict:
    """Return the effective POS config for a lv3 branch.

    Resolution order: lv3 (``StorePOSConfig``) → lv2 (``MerchantPOSConfig``).
    A blank field on the store means "inherit from the merchant".
    """
    store = getattr(lv3, 'pos_config', None)
    merchant = (
        store.merchant_config
        if store is not None
        else getattr(getattr(lv3, 'parent_lv2', None), 'pos_config', None)
    )

    def first(*vals):
        return next((v for v in vals if v is not None), None)

    tax = first(
        store.tax_pct if store else None,
        merchant.default_tax_pct if merchant else None,
    )
    service_charge = first(
        store.service_charge_pct if store else None,
        merchant.default_service_charge_pct if merchant else None,
    )
    stt_id = first(
        store.sub_transaction_type_id if store else None,
        merchant.sub_transaction_type_id if merchant else None,
    )
    qris = first(
        store.qris_image if store and store.qris_image else None,
        merchant.qris_image if merchant and merchant.qris_image else None,
    )

    return {
        'sub_transaction_type_id': stt_id,
        'sub_transaction_type': stt_id,
        'revenue_account_id': first(
            store.revenue_account_id if store else None,
            merchant.revenue_account_id if merchant else None,
        ),
        'offset_coa_account_id': first(
            store.offset_coa_account_id if store else None,
            merchant.offset_coa_account_id if merchant else None,
        ),
        'payment_account_id': first(
            store.default_payment_account_id if store else None,
            merchant.default_payment_account_id if merchant else None,
        ),
        'tax_pct': tax if tax is not None else Decimal('0'),
        'service_charge_pct': service_charge if service_charge is not None else Decimal('0'),
        'tax_inclusive': merchant.tax_inclusive if merchant else False,
        'currency': merchant.currency if merchant else 'IDR',
        'qris_image_url': qris.url if qris else None,
    }
