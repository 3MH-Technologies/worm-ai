"""Symmetric encryption for secrets at rest (API keys)."""

from __future__ import annotations

import base64
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

log = logging.getLogger(__name__)
_fernet: Fernet | None = None


def _derive_key(secret: str) -> bytes:
    """Derive a 32-byte url-safe base64 key from any string."""
    import hashlib
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        s = get_settings()
        key = s.encryption_key or s.jwt_secret
        if not key or key.startswith("change") or key.startswith("replace"):
            log.warning("encryption.key not configured; using jwt_secret fallback")
        try:
            f = Fernet(key.encode() if isinstance(key, str) else key)
        except (ValueError, TypeError):
            f = Fernet(_derive_key(key))
        _fernet = f
    return _fernet


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _get_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        log.error("decryption failed: %s", e)
        return ""
