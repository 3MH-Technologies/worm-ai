"""Pure unit tests for security primitives (no DB needed)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import jwt
import pytest

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


# ---- Password Hashing ----

class TestPasswordHash:
    def test_bcrypt_starts_with_2b(self):
        h = hash_password("hello-world")
        assert h.startswith("$2b$")

    def test_salts_are_unique(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2
        assert verify_password("same", h1)
        assert verify_password("same", h2)

    def test_wrong_password_rejected(self):
        h = hash_password("correct")
        assert not verify_password("wrong", h)

    def test_verify_graceful_on_bad_hash(self):
        assert not verify_password("x", "not-a-valid-hash")


# ---- JWT ----

class TestJWT:
    def test_access_token_structure(self):
        token = create_access_token(sub="abc123")
        payload = decode_token(token)
        assert payload["sub"] == "abc123"
        assert "role" not in payload
        assert payload["type"] == "access"
        assert "jti" in payload
        assert "iat" in payload
        assert "exp" in payload

    def test_access_ttl(self):
        token = create_access_token(sub="x")
        payload = decode_token(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        expected = datetime.now(tz=timezone.utc) + timedelta(minutes=30)
        assert abs((exp - expected).total_seconds()) < 10

    def test_session_id_in_access(self):
        token = create_access_token(sub="x", session_id="sess1")
        payload = decode_token(token)
        assert payload["sid"] == "sess1"

    def test_refresh_token_has_sid_and_type(self):
        token, exp = create_refresh_token(sub="x", session_id="sess1")
        payload = decode_token(token)
        assert payload["type"] == "refresh"
        assert payload["sid"] == "sess1"
        assert payload["sub"] == "x"

    def test_refresh_ttl_14_days(self):
        token, exp = create_refresh_token(sub="x", session_id="s")
        now = datetime.now(tz=timezone.utc)
        expected = now + timedelta(days=14)
        assert abs((exp - expected).total_seconds()) < 10

    def test_jti_uniqueness(self):
        jtis = {decode_token(create_access_token(sub="x"))["jti"] for _ in range(10)}
        assert len(jtis) == 10

    def test_expired_token_raises(self):
        expired = jwt.encode(
            {"sub": "x", "exp": 0, "iat": 0, "type": "access", "jti": "dead"},
            "test-jwt-secret-for-testing-only",
            algorithm="HS256",
        )
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_token(expired)

    def test_invalid_signature_rejected(self):
        tampered = jwt.encode(
            {"sub": "x", "exp": 9999999999, "iat": 0, "type": "access", "jti": "bad"},
            "different-secret",
            algorithm="HS256",
        )
        with pytest.raises(jwt.InvalidTokenError):
            decode_token(tampered)


# ---- CSRF ----

class TestCSRF:
    def test_new_token_length(self):
        t = new_csrf_token()
        assert len(t) == 43

    def test_hash_consistency(self):
        t = "test-token"
        assert hash_csrf(t) == hash_csrf(t)
        assert len(hash_csrf(t)) == 64

    def test_different_inputs_different_outputs(self):
        assert hash_csrf("a") != hash_csrf("b")


# ---- Device Fingerprint ----

class TestDeviceFingerprint:
    def test_length_and_hex(self):
        fp = device_fingerprint("UA", "1.2.3.4")
        assert len(fp) == 32
        int(fp, 16)

    def test_deterministic(self):
        assert device_fingerprint("A", "B") == device_fingerprint("A", "B")

    def test_different_ua_different_fp(self):
        assert device_fingerprint("A", "1") != device_fingerprint("B", "1")

    def test_different_ip_different_fp(self):
        assert device_fingerprint("A", "1") != device_fingerprint("A", "2")


# ---- Fernet Encryption ----

class TestEncryption:
    def test_roundtrip(self):
        original = "sk-proj-test-key-12345"
        encrypted = encrypt(original)
        assert encrypted != original
        assert encrypted.startswith("gAAAAA")
        assert decrypt(encrypted) == original

    def test_empty_returns_empty(self):
        assert encrypt("") == ""
        assert decrypt("") == ""

    def test_bad_ciphertext_returns_empty(self):
        assert decrypt("invalid-data") == ""

    def test_different_keys_different_ciphertexts(self):
        """Same plaintext should produce different ciphertexts (Fernet includes IV)."""
        pt = "same-value"
        c1 = encrypt(pt)
        c2 = encrypt(pt)
        assert c1 != c2
        assert decrypt(c1) == pt
        assert decrypt(c2) == pt
