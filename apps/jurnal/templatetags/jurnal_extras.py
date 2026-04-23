"""Custom template filters and tags for Indonesian date formatting."""
import datetime

from django import template
from django.utils import timezone

register = template.Library()

_HARI = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu']
_BULAN = [
    '', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
    'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember',
]


@register.filter(name='tanggal_id')
def tanggal_id(value):
    """Format a date to Indonesian long form: 'Kamis, 23 April 2026'.

    Accepts a YYYY-MM-DD string, a date object, or a datetime object.
    Returns '—' for empty/None values.
    """
    if not value:
        return '\u2014'
    if isinstance(value, datetime.datetime):
        value = value.date()
    if isinstance(value, str):
        try:
            value = datetime.date.fromisoformat(value)
        except (ValueError, AttributeError):
            return value
    if not isinstance(value, datetime.date):
        return str(value)
    return f'{_HARI[value.weekday()]}, {value.day} {_BULAN[value.month]} {value.year}'


@register.simple_tag
def now_id():
    """Return the current local date-time as 'Kamis, 23 April 2026  ·  14:30'."""
    now = timezone.localtime(timezone.now())
    return (
        f'{_HARI[now.weekday()]}, {now.day} {_BULAN[now.month]} {now.year}'
        f'\u00a0\u00a0\u00b7\u00a0\u00a0{now.strftime("%H:%M")}'
    )
