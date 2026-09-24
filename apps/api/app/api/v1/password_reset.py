"""Password reset (forgot/reset) flow."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from app.core.config import get_settings
from app.core.security import hash_password
from app.db import mongo
from app.services.audit import log_action

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str = Field(min_length=16, max_length=256)
    newPassword: str = Field(min_length=8, max_length=128)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@router.post("/forgot-password")
async def forgot_password(payload: ForgotIn, request: Request) -> dict:
    """Always returns 200 to avoid user-enumeration.

    In production this would email a link with `?token=...`. For self-hosted
    dev we return the token in the response when `ENV != production` so admins
    can complete the flow without an email gateway.
    """
    settings = get_settings()
    user = await mongo.users().find_one({"email": payload.email.lower()})
    response: dict = {"ok": True}
    if user:
        token = secrets.token_urlsafe(32)
        now = datetime.now(tz=UTC)
        await mongo.password_resets().insert_one({
            "userId": user["_id"],
            "tokenHash": _hash(token),
            "createdAt": now,
            "expiresAt": now + timedelta(hours=1),
            "usedAt": None,
            "ip": request.client.host if request.client else None,
        })
        await log_action(
            actor_id=str(user["_id"]),
            action="auth.password_reset_requested",
            resource=f"user:{user['_id']}",
            ip=request.client.host if request.client else None,
        )
        if settings.env != "production":
            response["devToken"] = token
    return response


@router.post("/reset-password", status_code=204)
async def reset_password(payload: ResetIn, request: Request) -> None:
    token_hash = _hash(payload.token)
    record = await mongo.password_resets().find_one({"tokenHash": token_hash, "usedAt": None})
    if not record:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or used token")
    if record["expiresAt"] < datetime.now(tz=UTC):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "token expired")

    user = await mongo.users().find_one({"_id": record["userId"]})
    if not user:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "user no longer exists")

    await mongo.users().update_one(
        {"_id": user["_id"]},
        {"$set": {"passwordHash": hash_password(payload.newPassword), "updatedAt": datetime.now(tz=UTC)}},
    )
    await mongo.password_resets().update_one(
        {"_id": record["_id"]},
        {"$set": {"usedAt": datetime.now(tz=UTC)}},
    )
    # revoke all refresh tokens for safety
    await mongo.refresh_tokens().update_many(
        {"userId": user["_id"], "revoked": False},
        {"$set": {"revoked": True, "revokedAt": datetime.now(tz=UTC)}},
    )
    await log_action(
        actor_id=str(user["_id"]),
        action="auth.password_reset_completed",
        resource=f"user:{user['_id']}",
        ip=request.client.host if request.client else None,
    )
    await mongo.notifications().insert_one({
        "userId": user["_id"],
        "title": "Your password was changed",
        "body": "If this was not you, please contact an administrator immediately.",
        "kind": "warning",
        "read": False,
        "createdAt": datetime.now(tz=UTC),
    })
