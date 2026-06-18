from django.test import TestCase
from apps.pendapatan.models import PendapatanHeader, StandarAkuntansi


class StandarAkuntansiTest(TestCase):
    def test_header_defaults_to_psak_71_72(self):
        header = PendapatanHeader()
        self.assertEqual(header.standar_akuntansi, StandarAkuntansi.PSAK_71_72)

    def test_choices_include_sak_etap(self):
        choices = [c[0] for c in StandarAkuntansi.choices]
        self.assertIn('SAK_ETAP', choices)
