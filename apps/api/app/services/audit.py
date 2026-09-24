"""Audit logging helper."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.db import mongo


async def log_action(
    *,
    actor_id: str | None,
    action: str,
    resource: str,
    ip: str | None = None,
    user_agent: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    await mongo.audit_logs().insert_one({
        "actorId": actor_id,
        "action": action,
        "resource": resource,
        "ipAddress": ip,
        "userAgent": user_agent,
        "metadata": metadata or {},
        "timestamp": datetime.now(tz=UTC),
    })
