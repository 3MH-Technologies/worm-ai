"""Memory engine: long-term, context, session, preferences."""

from __future__ import annotations

from datetime import UTC, datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import current_user
from app.db import mongo
from app.models.extras import MemoryCreate, MemoryItem

router = APIRouter(prefix="/memory", tags=["memory"])


def _to_out(doc: dict) -> MemoryItem:
    return MemoryItem(
        id=str(doc["_id"]),
        userId=str(doc["userId"]),
        kind=doc.get("kind", "long_term"),
        content=doc.get("content", ""),
        weight=doc.get("weight", 1.0),
        source=doc.get("source"),
        createdAt=doc.get("createdAt") or datetime.now(tz=UTC),
        lastUsedAt=doc.get("lastUsedAt"),
    )


@router.get("", response_model=list[MemoryItem])
async def list_memory(user=Depends(current_user)) -> list[MemoryItem]:
    docs = await mongo.memories().find({"userId": user["_id"]}).sort("createdAt", -1).limit(200).to_list(length=200)
    return [_to_out(d) for d in docs]


@router.post("", response_model=MemoryItem, status_code=status.HTTP_201_CREATED)
async def add_memory(payload: MemoryCreate, user=Depends(current_user)) -> MemoryItem:
    doc = {
        "userId": user["_id"],
        "kind": payload.kind,
        "content": payload.content,
        "weight": payload.weight,
        "source": payload.source,
        "createdAt": datetime.now(tz=UTC),
        "lastUsedAt": None,
    }
    res = await mongo.memories().insert_one(doc)
    doc["_id"] = res.inserted_id
    return _to_out(doc)


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(memory_id: str, user=Depends(current_user)) -> None:
    res = await mongo.memories().delete_one({"_id": ObjectId(memory_id), "userId": user["_id"]})
    if res.deleted_count == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "memory not found")


async def gather_for_chat(user_id: ObjectId, conversation_id: ObjectId | None = None) -> dict[str, list[str]]:
    """Pull memory slices used to build the system prompt for a chat turn."""
    docs = await mongo.memories().find({"userId": user_id}).sort("weight", -1).limit(80).to_list(length=80)
    grouped: dict[str, list[str]] = {
        "long_term": [], "context": [], "session": [], "preference": [], "summary": []
    }
    for d in docs:
        grouped.setdefault(d.get("kind", "long_term"), []).append(d.get("content", ""))
    return grouped
