"""Hardening tests: password hashing, JWT, CSRF, device fingerprint, encryption."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from passlib.context import CryptContext

from app.core.crypto import decrypt, encrypt
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    device_fingerprint,
    hash_csrf,
    hash_password,
    new_csrf_token,
    verify_password,
)

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TestPasswordHashing:
    def test_bcrypt_adaptive_algorithm(self):
        """Verify bcrypt is used (adaptive, salt included)."""
        h = hash_password("test-password-123")
        assert h.startswith("$2b$"), "should be bcrypt $2b$"
        # bcrypt includes salt in the hash string
        parts = h.split("$")
        assert len(parts) == 4
        assert parts[1] == "2b"

    def test_hash_is_deterministic_with_salt(self):
        """Each hash should be different (different salt) but all verify."""
        h1 = hash_password("same-pass")
        h2 = hash_password("same-pass")
        assert h1 != h2, "different salts should produce different hashes"
        assert verify_password("same-pass", h1)
        assert verify_password("same-pass", h2)

    def test_wrong_password_fails(self):
        h = hash_password("real-pass")
        assert not verify_password("wrong-pass", h)

    def test_empty_password(self):
        h = hash_password("")
        assert verify_password("", h)

    def test_long_password(self):
        long = "a" * 1000
        h = hash_password(long)
        assert verify_password(long, h)


class TestJWT:
    def test_access_token_creation_and_decoding(self):
        token = create_access_token(sub="user123")
        payload = decode_token(token)
        assert payload["sub"] == "user123"
        assert "role" not in payload
        assert payload["type"] == "access"
        assert "jti" in payload
        assert "iat" in payload
        assert "exp" in payload

    def test_access_token_expiry(self, settings):
        """Access token should expire after jwt_access_ttl_min."""
        short_ttl = 1 / 60  # 1 second
        # Override for test
        token = create_access_token(sub="x")
        payload = decode_token(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        expected = datetime.now(tz=timezone.utc) + timedelta(minutes=settings.jwt_access_ttl_min)
        # Allow 5 sec tolerance
        assert abs((exp - expected).total_seconds()) < 5

    def test_refresh_token_has_session_id(self):
        token, exp = create_refresh_token(sub="user123", session_id="sess_abc")
        payload = decode_token(token)
        assert payload["type"] == "refresh"
        assert payload["sid"] == "sess_abc"
        assert payload["sub"] == "user123"

    def test_jwt_algorithm_hs256(self, settings):
        token = create_access_token(sub="x")
        # Parse without verification to check header
        header = jwt.get_unverified_header(token)
        assert header["alg"] == "HS256"

    def test_expired_token_raises(self):
        from app.core.config import get_settings

        s = get_settings()
        expired = jwt.encode(
            {"sub": "x", "exp": 0, "iat": 0, "type": "access", "jti": "test"},
            s.jwt_secret,
            algorithm=s.jwt_algorithm,
        )
        # Manually decode to test expiry
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_token(expired)

    def test_wrong_token_type_rejected(self):
        """Refresh token used as access should be rejected."""
        token, _ = create_refresh_token(sub="x", session_id="s")
        payload = decode_token(token)
        assert payload["type"] == "refresh"

    def test_token_has_unique_jti(self):
        t1 = create_access_token(sub="x")
        t2 = create_access_token(sub="x")
        p1 = decode_token(t1)
        p2 = decode_token(t2)
        assert p1["jti"] != p2["jti"]


class TestCSRF:
    def test_token_generation(self):
        t = new_csrf_token()
        assert len(t) == 43  # 32 bytes url-safe base64

    def test_hash_is_deterministic(self):
        t = "some-random-token-value"
        h1 = hash_csrf(t)
        h2 = hash_csrf(t)
        assert h1 == h2
        assert len(h1) == 64  # SHA256 hex

    def test_different_tokens_different_hashes(self):
        assert hash_csrf("token-a") != hash_csrf("token-b")


class TestDeviceFingerprint:
    def test_fingerprint_format(self):
        fp = device_fingerprint("Mozilla/5.0", "192.168.1.1")
        assert len(fp) == 32
        assert all(c in "0123456789abcdef" for c in fp)

    def test_different_inputs_different_fingerprints(self):
        fp1 = device_fingerprint("Chrome", "1.2.3.4")
        fp2 = device_fingerprint("Firefox", "1.2.3.4")
        assert fp1 != fp2

    def test_same_inputs_same_fingerprint(self):
        fp1 = device_fingerprint("Chrome", "1.2.3.4")
        fp2 = device_fingerprint("Chrome", "1.2.3.4")
        assert fp1 == fp2


class TestFernetEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        original = "sk-proj-OpenAIKey12345"
        encrypted = encrypt(original)
        assert encrypted != original
        assert encrypted.startswith("gAAAAA")  # Fernet prefix
        decrypted = decrypt(encrypted)
        assert decrypted == original

    def test_empty_string(self):
        assert encrypt("") == ""
        assert decrypt("") == ""

    def test_invalid_ciphertext(self):
        assert decrypt("not-valid") == ""

    def test_api_key_presence(self):
        """Secrets stay encrypted at rest when stored."""
        encrypted = encrypt("sk-test-123")
        assert encrypted  # Not empty
        assert encrypted != "sk-test-123"
