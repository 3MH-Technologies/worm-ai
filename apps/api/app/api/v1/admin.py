"""Admin: user management, statistics, audit logs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import current_user, public_user
from app.cache.redis import client as redis_client
from app.db import mongo
from app.models.auth import AdminUserUpdateIn, AuditLogOut, UserListOut
from app.models.extras import AdminStats, ErrorEvent
from app.services.audit import log_action

router = APIRouter(prefix="/admin", tags=["admin"])


def _admin(user: dict) -> None:
    if user.get("role") not in ("admin", "superadmin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")


# ---- Users ----
@router.get("/users", response_model=UserListOut)
async def list_users(
    user=Depends(current_user),
    q: str | None = None,
    role: str | None = None,
    status_: str | None = Query(default=None, alias="status"),
    page: int = 1,
    size: int = 50,
) -> UserListOut:
    _admin(user)
    query: dict = {}
    if q:
        query["$or"] = [
            {"username": {"$regex": q, "$options": "i"}},
            {"email": {"$regex": q, "$options": "i"}},
        ]
    if role:
        query["role"] = role
    if status_:
        query["status"] = status_
    total = await mongo.users().count_documents(query)
    cursor = mongo.users().find(query).sort("createdAt", -1).skip((page - 1) * size).limit(size)
    docs = await cursor.to_list(length=size)
    return UserListOut(items=[public_user(d) for d in docs], total=total, page=page, size=size)


@router.patch("/users/{user_id}")
async def admin_update_user(user_id: str, payload: AdminUserUpdateIn, user=Depends(current_user)) -> dict:
    _admin(user)
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        target = await mongo.users().find_one({"_id": ObjectId(user_id)})
        if not target:
            raise HTTPException(404, "user not found")
        return public_user(target)
    # prevent privilege escalation: only superadmin can promote to admin/superadmin
    if updates.get("role") in ("admin", "superadmin") and user.get("role") != "superadmin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only superadmin can grant admin")
    if updates.get("role") == "developer" and user.get("role") not in ("admin", "superadmin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only can grant developer")
    updates["updatedAt"] = datetime.now(tz=timezone.utc)
    res = await mongo.users().update_one({"_id": ObjectId(user_id)}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(404, "user not found")
    target = await mongo.users().find_one({"_id": ObjectId(user_id)})
    await log_action(actor_id=str(user["_id"]), action="user.update", resource=f"user:{user_id}", metadata=updates)

    # Notify user of status change
    if "status" in updates:
        await mongo.notifications().insert_one({
            "userId": target["_id"],
            "title": "Account status updated",
            "body": f"Your account status is now '{updates['status']}'.",
            "kind": "success" if updates["status"] == "approved" else "warning",
            "read": False,
            "createdAt": datetime.now(tz=timezone.utc),
        })

    return public_user(target)


@router.post("/users/{user_id}/approve")
async def approve_user(user_id: str, user=Depends(current_user)) -> dict:
    _admin(user)
    res = await mongo.users().update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"status": "approved", "updatedAt": datetime.now(tz=timezone.utc)}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "user not found")
    await log_action(actor_id=str(user["_id"]), action="user.approve", resource=f"user:{user_id}")
    target = await mongo.users().find_one({"_id": ObjectId(user_id)})
    await mongo.notifications().insert_one({
        "userId": target["_id"],
        "title": "Welcome to WormGPT",
        "body": "Your account has been approved. You can now start chatting.",
        "kind": "success",
        "read": False,
        "createdAt": datetime.now(tz=timezone.utc),
    })
    return public_user(target)


@router.post("/users/{user_id}/reject")
async def reject_user(user_id: str, user=Depends(current_user)) -> dict:
    _admin(user)
    res = await mongo.users().update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"status": "rejected", "updatedAt": datetime.now(tz=timezone.utc)}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "user not found")
    await log_action(actor_id=str(user["_id"]), action="user.reject", resource=f"user:{user_id}")
    return public_user(await mongo.users().find_one({"_id": ObjectId(user_id)}))


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: str, user=Depends(current_user)) -> None:
    _admin(user)
    if str(user["_id"]) == user_id:
        raise HTTPException(400, "cannot delete yourself")
    res = await mongo.users().delete_one({"_id": ObjectId(user_id)})
    if res.deleted_count == 0:
        raise HTTPException(404, "user not found")
    await log_action(actor_id=str(user["_id"]), action="user.delete", resource=f"user:{user_id}")


# ---- Stats ----
@router.get("/stats", response_model=AdminStats)
async def get_stats(user=Depends(current_user)) -> AdminStats:
    _admin(user)
    now = datetime.now(tz=timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = now - timedelta(days=1)

    total_users = await mongo.users().count_documents({})
    pending_users = await mongo.users().count_documents({"status": "pending"})
    active_users = await mongo.users().count_documents({"lastLogin": {"$gte": yesterday}})
    total_conversations = await mongo.conversations().count_documents({})
    total_messages = await mongo.messages().count_documents({})
    messages_today = await mongo.messages().count_documents({"createdAt": {"$gte": today_start}})

    # tokens today from redis
    tokens_today = 0
    try:
        r = redis_client()
        today_key = today_start.strftime("%Y-%m-%d")
        async for key in r.scan_iter(f"usage:{today_key}:*"):
            tokens_today += int(await r.get(key) or 0)
    except Exception:
        pass
    total_tokens = await mongo.messages().aggregate([
        {"$group": {"_id": None, "sum": {"$sum": "$tokens"}}}
    ]).to_list(length=1)
    total_tokens_v = int(total_tokens[0]["sum"]) if total_tokens else 0

    from app.services.notrack import NOTRACK_MODELS
    active_models = len(NOTRACK_MODELS)

    # recent registrations
    recent_users = await mongo.users().find().sort("createdAt", -1).limit(8).to_list(length=8)
    recent_registrations = [public_user(u) for u in recent_users]

    # recent audit events
    recent_audit_docs = await mongo.audit_logs().find().sort("timestamp", -1).limit(10).to_list(length=10)
    actor_ids = list({d.get("actorId") for d in recent_audit_docs if d.get("actorId")})
    actor_map: dict[str, str] = {}
    if actor_ids:
        async for u in mongo.users().find({"_id": {"$in": [ObjectId(a) for a in actor_ids]}}, {"username": 1}):
            actor_map[str(u["_id"])] = u["username"]
    recent_audit = [
        AuditLogOut(
            id=str(d["_id"]),
            actorId=d.get("actorId") or "",
            actorUsername=actor_map.get(d.get("actorId") or ""),
            action=d["action"],
            resource=d.get("resource") or "",
            ipAddress=d.get("ipAddress"),
            userAgent=d.get("userAgent"),
            timestamp=d["timestamp"],
        )
        for d in recent_audit_docs
    ]

    # recent errors
    recent_err_docs = await mongo.errors_log().find().sort("createdAt", -1).limit(10).to_list(length=10)
    recent_errors = [
        ErrorEvent(
            id=str(d["_id"]),
            kind=d.get("kind", "server"),
            message=(d.get("message") or "")[:500],
            path=d.get("path"),
            method=d.get("method"),
            status=d.get("status"),
            actorId=d.get("actorId"),
            createdAt=d["createdAt"],
        )
        for d in recent_err_docs
    ]

    return AdminStats(
        totalUsers=total_users,
        pendingUsers=pending_users,
        activeUsers24h=active_users,
        totalConversations=total_conversations,
        totalMessages=total_messages,
        totalTokens=total_tokens_v,
        tokensToday=tokens_today,
        messagesToday=messages_today,
        activeModels=active_models,
        errorRate=0.0,
        revenue=0.0,
        generatedAt=now,
        recentRegistrations=recent_registrations,
        recentAudit=recent_audit,
        recentErrors=recent_errors,
    )


@router.get("/errors", response_model=list[ErrorEvent])
async def list_errors(user=Depends(current_user), limit: int = Query(default=50, le=200)) -> list[ErrorEvent]:
    _admin(user)
    docs = await mongo.errors_log().find().sort("createdAt", -1).limit(limit).to_list(length=limit)
    return [
        ErrorEvent(
            id=str(d["_id"]),
            kind=d.get("kind", "server"),
            message=(d.get("message") or "")[:500],
            path=d.get("path"),
            method=d.get("method"),
            status=d.get("status"),
            actorId=d.get("actorId"),
            createdAt=d["createdAt"],
        )
        for d in docs
    ]


# ---- Audit ----
@router.get("/audit-logs", response_model=list[AuditLogOut])
async def list_audit(
    user=Depends(current_user),
    action: str | None = None,
    actor: str | None = None,
    limit: int = Query(default=100, le=500),
) -> list[AuditLogOut]:
    _admin(user)
    q: dict = {}
    if action:
        q["action"] = action
    if actor:
        q["actorId"] = actor
    docs = await mongo.audit_logs().find(q).sort("timestamp", -1).limit(limit).to_list(length=limit)
    # hydrate actor username
    actor_ids = list({d["actorId"] for d in docs if d.get("actorId")})
    actors: dict[str, str] = {}
    if actor_ids:
        async for u in mongo.users().find({"_id": {"$in": [ObjectId(a) for a in actor_ids]}}, {"username": 1}):
            actors[str(u["_id"])] = u["username"]
    return [
        AuditLogOut(
            id=str(d["_id"]),
            actorId=d.get("actorId") or "",
            actorUsername=actors.get(d.get("actorId") or ""),
            action=d["action"],
            resource=d.get("resource") or "",
            ipAddress=d.get("ipAddress"),
            userAgent=d.get("userAgent"),
            timestamp=d["timestamp"],
        )
        for d in docs
    ]
