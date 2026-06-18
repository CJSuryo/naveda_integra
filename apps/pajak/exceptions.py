class TarifPajakTidakDitemukan(Exception):
    """No active TarifPajak found for given jenis_pajak and date."""


class MasaPajakTerkunciError(Exception):
    """Attempted to post to a locked MasaPajak period."""


class PajakStatusError(Exception):
    """PajakTransaksi is in an invalid status for the requested operation."""
