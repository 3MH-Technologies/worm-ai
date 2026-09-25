"""FastAPI dependencies: current user, rate limiting."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any

import jwt
from bson import ObjectId
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.cache.redis import allow
from app.core.config import get_settings
from app.core.security import decode_token
from app.db import mongo

log = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


async def _token_user(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token expired") from None
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from None
    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong token type")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing subject")
    user = await mongo.users().find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    if user.get("status") in ("suspended", "rejected"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "account disabled")
    return user


async def current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict[str, Any]:
    user = await _token_user(creds.credentials if creds else None)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
    return user


async def optional_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict[str, Any] | None:
    try:
        return await _token_user(creds.credentials if creds else None)
    except HTTPException:
        return None


async def rate_limit(
    request: Request,
    user: dict[str, Any] | None = Depends(optional_user),
) -> None:
    settings = get_settings()
    if user:
        ident = f"user:{user['_id']}"
    else:
        ip = request.client.host if request.client else "0.0.0.0"
        xff = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        ident = f"ip:{xff or ip}"
    key = f"rl:{ident}"
    try:
        ok = await allow(key, settings.rate_limit_per_min, 60)
    except RuntimeError:
        # Redis isn't up (fresh deploy / missing REDIS_URL). Serving the
        # request beats failing every call, so we fail open here.
        log.warning("rate limiter unavailable; allowing request")
        return
    if not ok:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate limit exceeded")


async def update_last_login(user_id: ObjectId) -> None:
    await mongo.users().update_one(
        {"_id": user_id},
        {"$set": {"lastLogin": datetime.now(tz=UTC)}},
    )


def public_user(u: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(u["_id"]),
        "username": u["username"],
        "email": u["email"],
        "status": u.get("status", "approved"),
        "avatar": u.get("avatar"),
        "createdAt": u.get("createdAt"),
        "lastLogin": u.get("lastLogin"),
    }
