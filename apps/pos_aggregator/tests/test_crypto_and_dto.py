from decimal import Decimal

from django.test import TestCase, override_settings

from pos_aggregator import crypto
from pos_aggregator.dto import CanonicalModifier, CanonicalOrderItem, money


class CryptoTest(TestCase):
    def test_roundtrip(self):
        self.assertEqual(crypto.decrypt(crypto.encrypt('s3cret')), 's3cret')

    def test_empty_stays_empty(self):
        self.assertEqual(crypto.encrypt(''), '')
        self.assertEqual(crypto.decrypt(''), '')

    def test_ciphertext_is_not_plaintext(self):
        self.assertNotIn('s3cret', crypto.encrypt('s3cret'))

    def test_mask_hides_all_but_tail(self):
        self.assertEqual(crypto.mask('abcdefghij'), '••••••••ghij')

    def test_mask_of_short_value_reveals_nothing(self):
        self.assertEqual(crypto.mask('abc'), '•••')

    def test_undecryptable_value_raises_actionable_error(self):
        with self.assertRaises(crypto.DecryptionError):
            crypto.decrypt('not-a-fernet-token')

    def test_warns_when_no_explicit_key_configured(self):
        with override_settings(AGGREGATOR_ENCRYPTION_KEY=''):
            self.assertTrue(crypto.check_encryption_config())

    def test_no_warning_with_explicit_key(self):
        from cryptography.fernet import Fernet
        with override_settings(AGGREGATOR_ENCRYPTION_KEY=Fernet.generate_key().decode()):
            self.assertEqual(crypto.check_encryption_config(), [])


class MoneyTest(TestCase):
    def test_returns_decimal_never_float(self):
        self.assertIsInstance(money('1000'), Decimal)
        self.assertIsInstance(money(10.5), Decimal)

    def test_minor_units_divisor(self):
        self.assertEqual(money(150000, divisor=100), Decimal('1500.00'))

    def test_none_and_blank_are_zero(self):
        self.assertEqual(money(None), Decimal('0'))
        self.assertEqual(money(''), Decimal('0'))

    def test_rounds_half_up_to_two_places(self):
        self.assertEqual(money('1.005'), Decimal('1.01'))

    def test_float_input_does_not_leak_binary_error(self):
        # 0.1 + 0.2 in float is 0.30000000000000004; going through str() and
        # Decimal must land exactly on 0.30.
        self.assertEqual(money(0.1) + money(0.2), Decimal('0.30'))


class OrderItemTotalsTest(TestCase):
    def test_line_total_includes_modifiers_per_unit(self):
        item = CanonicalOrderItem(
            external_id='1', name='Kopi', quantity=Decimal('2'),
            unit_price=Decimal('10000'),
            modifiers=[
                CanonicalModifier(external_id='m1', name='Extra shot',
                                  price=Decimal('5000'), quantity=Decimal('1')),
            ],
        )
        self.assertEqual(item.modifier_total, Decimal('5000.00'))
        self.assertEqual(item.line_total, Decimal('30000.00'))

    def test_line_total_without_modifiers(self):
        item = CanonicalOrderItem(
            external_id='1', name='Teh', quantity=Decimal('3'),
            unit_price=Decimal('7500'),
        )
        self.assertEqual(item.line_total, Decimal('22500.00'))
