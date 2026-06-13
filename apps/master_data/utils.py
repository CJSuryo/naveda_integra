"""Master data utility functions."""
from apps.master_data.models import Akun


def natural_sort_key(kode: str) -> list:
    """Return sort key ordering kode_akun values numerically per segment.

    '1.1.2' → [1, 1, 2]  <  '1.1.10' → [1, 1, 10]
    Non-numeric segments sort as 0 to keep non-standard kodes together.
    """
    parts = []
    for part in kode.split('.'):
        try:
            parts.append((0, int(part)))
        except ValueError:
            parts.append((1, part))
    return parts


def get_akun_sorted() -> list[Akun]:
    """Return all Akun records sorted naturally by kode_akun."""
    return sorted(Akun.objects.all(), key=lambda a: natural_sort_key(a.kode_akun))


def akun_sorted_queryset(filter_kwargs: dict | None = None):
    """Return an Akun QuerySet ordered by natural kode_akun sort.

    Fetches matching Akun objects, sorts in Python via natural_sort_key,
    then returns a properly ordered QuerySet using Case/When annotation.
    Must be called inside form __init__ (evaluates eagerly — not safe at class level).
    """
    from django.db.models import Case, IntegerField, Value, When

    qs = Akun.objects.all()
    if filter_kwargs:
        qs = qs.filter(**filter_kwargs)
    sorted_list = sorted(list(qs), key=lambda a: natural_sort_key(a.kode_akun))
    if not sorted_list:
        return Akun.objects.none()
    ordering = Case(
        *[When(pk=a.pk, then=Value(i)) for i, a in enumerate(sorted_list)],
        output_field=IntegerField(),
    )
    return Akun.objects.filter(pk__in=[a.pk for a in sorted_list]).annotate(_sk=ordering).order_by('_sk')
