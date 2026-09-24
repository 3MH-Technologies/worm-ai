"""Notifications endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import current_user
from app.db import mongo
from app.models.auth import NotificationOut

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
async def list_notifications(user=Depends(current_user)) -> list[NotificationOut]:
    docs = await mongo.notifications().find({"userId": user["_id"]}).sort("createdAt", -1).limit(100).to_list(length=100)
    return [NotificationOut(
        id=str(d["_id"]),
        title=d["title"],
        body=d.get("body", ""),
        read=d.get("read", False),
        createdAt=d["createdAt"],
        kind=d.get("kind", "info"),
    ) for d in docs]


@router.post("/{nid}/read", response_model=NotificationOut)
async def mark_read(nid: str, user=Depends(current_user)) -> NotificationOut:
    res = await mongo.notifications().find_one_and_update(
        {"_id": ObjectId(nid), "userId": user["_id"]},
        {"$set": {"read": True, "readAt": datetime.now(tz=UTC)}},
        return_document=True,
    )
    if not res:
        raise HTTPException(404, "notification not found")
    return NotificationOut(
        id=str(res["_id"]), title=res["title"], body=res.get("body", ""),
        read=res.get("read", False), createdAt=res["createdAt"], kind=res.get("kind", "info"),
    )


@router.post("/read-all")
async def mark_all_read(user=Depends(current_user)) -> dict:
    res = await mongo.notifications().update_many(
        {"userId": user["_id"], "read": False},
        {"$set": {"read": True, "readAt": datetime.now(tz=UTC)}},
    )
    return {"updated": res.modified_count}


@router.delete("/{nid}", status_code=204)
async def delete_notification(nid: str, user=Depends(current_user)) -> None:
    res = await mongo.notifications().delete_one({"_id": ObjectId(nid), "userId": user["_id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, "notification not found")
