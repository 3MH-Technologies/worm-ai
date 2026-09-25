"""Password hashing, JWT, CSRF, audit helpers."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings

log = logging.getLogger(__name__)


# ---- Password ----
def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except Exception:
        return False


# ---- JWT ----
def create_access_token(
    *,
    sub: str,
    session_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    s = get_settings()
    now = datetime.now(tz=UTC)
    payload: dict[str, Any] = {
        "sub": sub,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=s.jwt_access_ttl_min)).timestamp()),
        "type": "access",
        "jti": secrets.token_urlsafe(16),
    }
    if session_id:
        payload["sid"] = session_id
    if extra:
        payload.update(extra)
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def create_refresh_token(*, sub: str, session_id: str) -> tuple[str, datetime]:
    s = get_settings()
    now = datetime.now(tz=UTC)
    exp = now + timedelta(days=s.jwt_refresh_ttl_day)
    payload = {
        "sub": sub,
        "sid": session_id,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "type": "refresh",
        "jti": secrets.token_urlsafe(24),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm), exp


def decode_token(token: str) -> dict[str, Any]:
    s = get_settings()
    return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])


# ---- CSRF ----
def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def hash_csrf(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---- Device fingerprint ----
def device_fingerprint(user_agent: str, ip: str) -> str:
    return hashlib.sha256(f"{user_agent}|{ip}".encode()).hexdigest()[:32]
