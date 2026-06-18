from django.test import TestCase
from apps.pendapatan.models import PendapatanHeader, StandarAkuntansi


class StandarAkuntansiTest(TestCase):
    def test_header_defaults_to_psak_71_72(self):
        header = PendapatanHeader()
        self.assertEqual(header.standar_akuntansi, StandarAkuntansi.PSAK_71_72)

    def test_choices_include_sak_etap(self):
        choices = [c[0] for c in StandarAkuntansi.choices]
        self.assertIn('SAK_ETAP', choices)


from apps.pendapatan.models import KewajibabPelaksanaan


class KewajibabPelaksanaanModelTest(TestCase):
    def test_recognition_type_defaults_to_point_in_time(self):
        kp = KewajibabPelaksanaan()
        self.assertEqual(kp.recognition_type, KewajibabPelaksanaan.RecognitionType.POINT_IN_TIME)

    def test_harga_j_defaults_to_zero(self):
        from decimal import Decimal
        kp = KewajibabPelaksanaan()
        self.assertEqual(kp.harga_j, Decimal('0'))


from apps.pendapatan.models import JadwalPengakuan


class JadwalPengakuanModelTest(TestCase):
    def test_nilai_belum_diakui_property(self):
        from decimal import Decimal
        jadwal = JadwalPengakuan()
        jadwal.nilai_total = Decimal('1000')
        jadwal.nilai_diakui = Decimal('300')
        self.assertEqual(jadwal.nilai_belum_diakui, Decimal('700'))

    def test_defaults(self):
        from decimal import Decimal
        jadwal = JadwalPengakuan()
        self.assertEqual(jadwal.nilai_diakui, Decimal('0'))
        self.assertEqual(jadwal.status, JadwalPengakuan.Status.ACTIVE)
