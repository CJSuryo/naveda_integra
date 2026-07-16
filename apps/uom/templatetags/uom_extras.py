"""Custom template filters for the uom app."""
from django import template
from django.utils.formats import number_format

register = template.Library()


@register.filter(name='trim_decimal')
def trim_decimal(value):
    """Render a Decimal without trailing zeroes, e.g. 1000.00000000 -> '1000',
    0.00100000 -> '0,001' (locale-aware decimal separator).

    Returns '-' for None.
    """
    if value is None:
        return '-'
    return number_format(value.normalize(), use_l10n=True)
