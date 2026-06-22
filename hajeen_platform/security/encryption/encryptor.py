"""Encryptor — AES-256-GCM encryption for sensitive data at rest."""
from __future__ import annotations

import base64
import os
from typing import Tuple

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

ENCRYPTION_KEY_ENV = "ENCRYPTION_KEY"
KEY_SIZE = 32
NONCE_SIZE = 12
SALT_SIZE = 16


class DataEncryptor:
    """AES-256-GCM encryption for sensitive fields."""

    def __init__(self, key: Optional[bytes] = None) -> None:
        if key:
            self._key = key
        else:
            raw = os.environ.get(ENCRYPTION_KEY_ENV, "")
            if not raw:
                raise RuntimeError(f"{ENCRYPTION_KEY_ENV} not set")
            self._key = self._derive_key(raw.encode())

    def encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(NONCE_SIZE)
        aesgcm = AESGCM(self._key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
        combined = nonce + ciphertext
        return base64.urlsafe_b64encode(combined).decode()

    def decrypt(self, encrypted: str) -> str:
        combined = base64.urlsafe_b64decode(encrypted.encode())
        nonce = combined[:NONCE_SIZE]
        ciphertext = combined[NONCE_SIZE:]
        aesgcm = AESGCM(self._key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode()

    def _derive_key(self, raw: bytes) -> bytes:
        salt = hashlib.sha256(raw).digest()[:SALT_SIZE]
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=KEY_SIZE,
            salt=salt,
            iterations=480000,
            backend=default_backend(),
        )
        return kdf.derive(raw)


import hashlib
from typing import Optional
