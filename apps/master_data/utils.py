"""Master data utility functions."""
from apps.master_data.models import Akun


def natural_sort_key(kode: str) -> list[int]:
    """Return a sort key that orders kode_akun values naturally.

    '1.1.2' → [1, 1, 2]
    '1.1.10' → [1, 1, 10]
    So 1.1.2 < 1.1.10 (numeric comparison instead of lexicographic).
    """
    parts: list[int] = []
    for part in kode.split('.'):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return parts


def get_akun_sorted() -> list[Akun]:
    """Return all Akun records sorted naturally by kode_akun."""
    return sorted(
        Akun.objects.all(),
        key=lambda a: natural_sort_key(a.kode_akun),
    )
