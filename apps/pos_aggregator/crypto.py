"""Encryption for aggregator credentials at rest.

Client secrets, webhook signing keys and OAuth tokens are the keys to a
merchant's storefront: with them an attacker can read every order and rewrite
the published menu. They are therefore never stored as plaintext.

Key resolution:

1. ``settings.AGGREGATOR_ENCRYPTION_KEY`` — a urlsafe base64 Fernet key. This is
   what production must set.
2. Otherwise a key derived from ``SECRET_KEY`` via HKDF. This keeps development
   and tests working without extra setup, at the cost of tying ciphertexts to
   ``SECRET_KEY``.

Rotating ``SECRET_KEY`` while relying on the derived key makes existing
ciphertexts undecryptable. ``check_encryption_config()`` surfaces that risk.
"""
import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class DecryptionError(Exception):
    """Raised when stored ciphertext cannot be decrypted with the current key."""


def _derive_key_from_secret() -> bytes:
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b'naveda-pos-aggregator-v1',
        info=b'aggregator-credential-encryption',
    )
    return base64.urlsafe_b64encode(hkdf.derive(settings.SECRET_KEY.encode()))


def _fernet() -> Fernet:
    configured = getattr(settings, 'AGGREGATOR_ENCRYPTION_KEY', '')
    if configured:
        try:
            return Fernet(configured.encode() if isinstance(configured, str) else configured)
        except (ValueError, TypeError) as exc:
            raise ImproperlyConfigured(
                'AGGREGATOR_ENCRYPTION_KEY is not a valid Fernet key. Generate one with: '
                'python -c "from cryptography.fernet import Fernet; '
                'print(Fernet.generate_key().decode())"'
            ) from exc
    return Fernet(_derive_key_from_secret())


def encrypt(plaintext: str) -> str:
    """Encrypt a secret for storage. Empty input stays empty."""
    if not plaintext:
        return ''
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a stored secret. Empty input stays empty."""
    if not ciphertext:
        return ''
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise DecryptionError(
            'Stored aggregator credential could not be decrypted. This usually '
            'means AGGREGATOR_ENCRYPTION_KEY changed, or SECRET_KEY changed '
            'while no explicit AGGREGATOR_ENCRYPTION_KEY was set. The affected '
            'credential must be re-entered.'
        ) from exc


def mask(plaintext: str, visible: int = 4) -> str:
    """Render a secret for display: never show more than the last few chars."""
    if not plaintext:
        return '—'
    if len(plaintext) <= visible:
        return '•' * len(plaintext)
    return '•' * 8 + plaintext[-visible:]


def check_encryption_config() -> list[str]:
    """Return human-readable warnings about the current key setup."""
    warnings = []
    if not getattr(settings, 'AGGREGATOR_ENCRYPTION_KEY', ''):
        warnings.append(
            'AGGREGATOR_ENCRYPTION_KEY is not set — credential encryption is '
            'derived from SECRET_KEY. Rotating SECRET_KEY will make all stored '
            'aggregator credentials unreadable. Set an explicit key in production.'
        )
    return warnings
