"""Sessions + devices: list, revoke."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.deps import current_user
from app.core.security import device_fingerprint
from app.db import mongo
from app.services.audit import log_action

router = APIRouter(prefix="/security", tags=["security"])


class SessionOut(BaseModel):
    id: str
    kind: Literal["session", "device"]
    userAgent: str | None = None
    ip: str | None = None
    firstSeen: datetime | None = None
    lastSeen: datetime | None = None
    revoked: bool = False
    current: bool = False
    fingerprint: str | None = None


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(user=Depends(current_user), request: Request = None) -> list[SessionOut]:
    """Combine refresh-token records and device fingerprints into a single list,
    marking the current device/session as `current: true`."""
    out: list[SessionOut] = []
    current_fp = ""
    if request is not None:
        current_fp = device_fingerprint(
            request.headers.get("user-agent", ""),
            request.client.host if request.client else "",
        )

    async for d in mongo.devices().find({"userId": user["_id"]}).sort("lastSeen", -1).limit(50):
        out.append(SessionOut(
            id=str(d["_id"]),
            kind="device",
            userAgent=d.get("userAgent"),
            ip=d.get("ip"),
            firstSeen=d.get("firstSeen"),
            lastSeen=d.get("lastSeen"),
            revoked=bool(d.get("revokedAt")),
            current=d.get("fingerprint") == current_fp,
            fingerprint=d.get("fingerprint"),
        ))

    async for r in mongo.refresh_tokens().find({"userId": user["_id"], "revoked": False}).sort("createdAt", -1).limit(50):
        out.append(SessionOut(
            id=str(r["_id"]),
            kind="session",
            userAgent=r.get("userAgent"),
            ip=r.get("ip"),
            firstSeen=r.get("createdAt"),
            lastSeen=r.get("lastSeen"),
            revoked=False,
            current=False,
            fingerprint=None,
        ))

    return out


@router.post("/sessions/{session_id}/revoke", status_code=204)
async def revoke_session(session_id: str, user=Depends(current_user), request: Request = None) -> None:
    """Revoke a device (and its sessions) or an individual refresh token."""
    if not ObjectId.is_valid(session_id):
        raise HTTPException(400, "invalid id")
    oid = ObjectId(session_id)

    # Try device first
    res = await mongo.devices().update_one(
        {"_id": oid, "userId": user["_id"]},
        {"$set": {"revokedAt": datetime.now(tz=UTC)}},
    )
    if res.matched_count:
        # also revoke any refresh tokens that came from this device (matching ip+ua)
        dev = await mongo.devices().find_one({"_id": oid})
        if dev:
            await mongo.refresh_tokens().update_many(
                {"userId": user["_id"], "ip": dev.get("ip"), "userAgent": dev.get("userAgent"), "revoked": False},
                {"$set": {"revoked": True, "revokedAt": datetime.now(tz=UTC)}},
            )
        await log_action(
            actor_id=str(user["_id"]), action="security.device_revoked",
            resource=f"device:{session_id}",
            ip=request.client.host if request and request.client else None,
        )
        return

    # Try refresh token
    res = await mongo.refresh_tokens().update_one(
        {"_id": oid, "userId": user["_id"], "revoked": False},
        {"$set": {"revoked": True, "revokedAt": datetime.now(tz=UTC)}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "session not found")
    await log_action(
        actor_id=str(user["_id"]), action="security.session_revoked",
        resource=f"session:{session_id}",
    )


@router.post("/sessions/revoke-others", status_code=204)
async def revoke_other_sessions(user=Depends(current_user), request: Request = None) -> None:
    """Revoke every refresh token not matching the current device fingerprint."""
    if request is None:
        return
    current_fp = device_fingerprint(
        request.headers.get("user-agent", ""),
        request.client.host if request.client else "",
    )
    dev = await mongo.devices().find_one({"userId": user["_id"], "fingerprint": current_fp})
    if not dev:
        return
    await mongo.refresh_tokens().update_many(
        {"userId": user["_id"], "revoked": False, "$or": [
            {"ip": {"$ne": dev.get("ip")}},
            {"userAgent": {"$ne": dev.get("userAgent")}},
        ]},
        {"$set": {"revoked": True, "revokedAt": datetime.now(tz=UTC)}},
    )
    await log_action(actor_id=str(user["_id"]), action="security.other_sessions_revoked", resource=f"user:{user['_id']}")


@router.post("/sessions/cleanup", status_code=204)
async def cleanup_sessions(user=Depends(current_user)) -> None:
    """Permanently delete revoked sessions and devices."""
    await mongo.refresh_tokens().delete_many({
        "userId": user["_id"], "revoked": True,
    })
    await mongo.devices().delete_many({
        "userId": user["_id"], "revokedAt": {"$ne": None},
    })
    await log_action(
        actor_id=str(user["_id"]), action="security.sessions_cleaned",
        resource=f"user:{user['_id']}",
    )
