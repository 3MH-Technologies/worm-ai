"""Authentication endpoints: register, login, refresh, logout, me."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import current_user, public_user
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    device_fingerprint,
    hash_password,
    new_csrf_token,
    verify_password,
)
from app.db import mongo
from app.models.auth import (
    LoginIn,
    PasswordChangeIn,
    RefreshIn,
    RegisterIn,
    TokenPair,
    UserUpdateIn,
)
from app.services.audit import log_action

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

settings = get_settings()


async def _build_tokens(user: dict, request: Request) -> TokenPair:
    uid = str(user["_id"])
    session_id = new_csrf_token()
    access = create_access_token(sub=uid, session_id=session_id)
    refresh, exp = create_refresh_token(sub=uid, session_id=session_id)
    # Persist refresh token for rotation / revocation tracking
    await mongo.refresh_tokens().insert_one({
        "token": refresh,
        "userId": user["_id"],
        "sessionId": session_id,
        "ip": request.client.host if request.client else None,
        "userAgent": request.headers.get("user-agent"),
        "createdAt": datetime.now(tz=UTC),
        "expiresAt": exp,
        "revoked": False,
        "revokedAt": None,
    })
    return TokenPair(
        accessToken=access,
        refreshToken=refresh,
        expiresIn=settings.jwt_access_ttl_min * 60,
        user=public_user(user),  # type: ignore[arg-type]
    )


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterIn, request: Request) -> TokenPair:
    existing = await mongo.users().find_one({"$or": [{"email": payload.email.lower()}, {"username": payload.username}]})
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "email or username already in use")

    now = datetime.now(tz=UTC)
    doc = {
        "username": payload.username,
        "email": payload.email.lower(),
        "passwordHash": hash_password(payload.password),
        "status": "approved",  # instant access — no approval workflow
        "avatar": None,
        "createdAt": now,
        "updatedAt": now,
        "lastLogin": None,
        "failedLoginAttempts": 0,
        "lockedUntil": None,
    }
    result = await mongo.users().insert_one(doc)
    doc["_id"] = result.inserted_id

    # device record
    fp = device_fingerprint(request.headers.get("user-agent", ""), request.client.host if request.client else "")
    await mongo.devices().insert_one({
        "userId": result.inserted_id,
        "fingerprint": fp,
        "userAgent": request.headers.get("user-agent"),
        "ip": request.client.host if request.client else None,
        "firstSeen": now,
        "lastSeen": now,
        "trusted": True,
    })

    await log_action(
        actor_id=str(result.inserted_id),
        action="auth.register",
        resource=f"user:{result.inserted_id}",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return await _build_tokens(doc, request)


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginIn, request: Request) -> TokenPair:
    user = await mongo.users().find_one({"email": payload.email.lower()})
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    if user.get("lockedUntil") and user["lockedUntil"] > datetime.now(tz=UTC):
        raise HTTPException(status.HTTP_423_LOCKED, "account temporarily locked")

    if not verify_password(payload.password, user["passwordHash"]):
        attempts = (user.get("failedLoginAttempts") or 0) + 1
        update: dict = {"failedLoginAttempts": attempts}
        if attempts >= 8:
            from datetime import timedelta
            update["lockedUntil"] = datetime.now(tz=UTC) + timedelta(minutes=15)
            update["failedLoginAttempts"] = 0
        await mongo.users().update_one({"_id": user["_id"]}, {"$set": update})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    # record device
    fp = device_fingerprint(request.headers.get("user-agent", ""), request.client.host if request.client else "")
    await mongo.devices().update_one(
        {"userId": user["_id"], "fingerprint": fp},
        {"$set": {"lastSeen": datetime.now(tz=UTC)}, "$setOnInsert": {
            "userId": user["_id"], "fingerprint": fp,
            "userAgent": request.headers.get("user-agent"),
            "ip": request.client.host if request.client else None,
            "firstSeen": datetime.now(tz=UTC),
            "trusted": False,
        }},
        upsert=True,
    )

    await mongo.users().update_one(
        {"_id": user["_id"]},
        {"$set": {"failedLoginAttempts": 0, "lockedUntil": None, "lastLogin": datetime.now(tz=UTC)}},
    )
    user["lastLogin"] = datetime.now(tz=UTC)
    user["failedLoginAttempts"] = 0
    user["lockedUntil"] = None

    await log_action(
        actor_id=str(user["_id"]),
        action="auth.login",
        resource=f"user:{user['_id']}",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return await _build_tokens(user, request)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshIn, request: Request) -> TokenPair:
    import jwt
    try:
        data = decode_token(payload.refreshToken)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "refresh expired") from None
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid refresh token") from None
    if data.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong token type")
    stored = await mongo.refresh_tokens().find_one({"token": payload.refreshToken, "revoked": False})
    if not stored:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "refresh token revoked or reused")
    # Rotation: revoke the old token immediately (prevents token reuse on theft)
    now_dt = datetime.now(tz=UTC)
    await mongo.refresh_tokens().update_one(
        {"_id": stored["_id"]},
        {"$set": {"revoked": True, "revokedAt": now_dt}},
    )
    user = await mongo.users().find_one({"_id": ObjectId(data["sub"])})
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    return await _build_tokens(user, request)


@router.post("/logout", status_code=204)
async def logout(payload: RefreshIn, user=Depends(current_user)) -> None:  # type: ignore[assignment]
    await mongo.refresh_tokens().update_one(
        {"token": payload.refreshToken},
        {"$set": {"revoked": True, "revokedAt": datetime.now(tz=UTC)}},
    )
    await log_action(actor_id=str(user["_id"]), action="auth.logout", resource=f"user:{user['_id']}")


@router.post("/logout-all", status_code=204)
async def logout_all(user=Depends(current_user)) -> None:
    """Revoke ALL refresh tokens and invalidate all devices for the current user."""
    now = datetime.now(tz=UTC)
    await mongo.refresh_tokens().update_many(
        {"userId": user["_id"], "revoked": False},
        {"$set": {"revoked": True, "revokedAt": now}},
    )
    await mongo.devices().update_many(
        {"userId": user["_id"]},
        {"$set": {"revokedAt": now}},
    )
    await log_action(actor_id=str(user["_id"]), action="auth.logout_all", resource=f"user:{user['_id']}")


@router.get("/me")
async def me(user=Depends(current_user)) -> dict:
    return public_user(user)


@router.patch("/me")
async def update_me(payload: UserUpdateIn, user=Depends(current_user)) -> dict:
    # exclude_unset (not exclude_none): an explicit `avatar: null` means "clear the
    # avatar" and must reach Mongo, while an omitted field stays untouched.
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    if not updates:
        return public_user(user)
    updates["updatedAt"] = datetime.now(tz=UTC)
    await mongo.users().update_one({"_id": user["_id"]}, {"$set": updates})
    fresh = await mongo.users().find_one({"_id": user["_id"]})
    return public_user(fresh)


@router.post("/change-password", status_code=204)
async def change_password(payload: PasswordChangeIn, user=Depends(current_user)) -> None:  # type: ignore[assignment]
    if not verify_password(payload.oldPassword, user["passwordHash"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "old password is incorrect")
    await mongo.users().update_one(
        {"_id": user["_id"]},
        {"$set": {"passwordHash": hash_password(payload.newPassword), "updatedAt": datetime.now(tz=UTC)}},
    )
    await log_action(actor_id=str(user["_id"]), action="auth.password_changed", resource=f"user:{user['_id']}")
