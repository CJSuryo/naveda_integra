from django.test import TestCase
from apps.pajak.exceptions import TarifPajakTidakDitemukan, MasaPajakTerkunciError, PajakStatusError


class ExceptionSmokeTest(TestCase):
    def test_exceptions_importable(self):
        self.assertTrue(issubclass(TarifPajakTidakDitemukan, Exception))
        self.assertTrue(issubclass(MasaPajakTerkunciError, Exception))
        self.assertTrue(issubclass(PajakStatusError, Exception))
