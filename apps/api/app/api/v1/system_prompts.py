"""System prompt management. Content is NEVER returned to non-admin users."""

from __future__ import annotations

from datetime import UTC, datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import current_user
from app.db import mongo
from app.models.models import (
    SystemPromptCreate,
    SystemPromptOut,
    SystemPromptSummary,
    SystemPromptUpdate,
    SystemPromptVersion,
)
from app.services.audit import log_action

router = APIRouter(prefix="/system-prompts", tags=["system-prompts"])


async def _is_admin(user: dict) -> bool:
    return user.get("role") in ("developer", "admin", "superadmin")


def _summary(doc: dict) -> SystemPromptSummary:
    return SystemPromptSummary(
        id=str(doc["_id"]),
        name=doc["name"],
        description=doc.get("description"),
    )


def _out(doc: dict) -> SystemPromptOut:
    versions = [
        SystemPromptVersion(
            version=v["version"],
            content=v["content"],
            changelog=v.get("changelog"),
            createdAt=v["createdAt"],
        )
        for v in doc.get("versions", [])
    ]
    return SystemPromptOut(
        id=str(doc["_id"]),
        name=doc["name"],
        description=doc.get("description"),
        tags=doc.get("tags", []),
        active=doc.get("active", True),
        currentVersion=doc.get("currentVersion", 1),
        versions=versions,
        createdAt=doc.get("createdAt") or datetime.now(tz=UTC),
        updatedAt=doc.get("updatedAt") or datetime.now(tz=UTC),
    )


@router.get("", response_model=list[SystemPromptOut])
async def list_prompts(user=Depends(current_user)) -> list[SystemPromptOut]:
    """Full content visible only to admins. Other users get 403."""
    if not await _is_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    docs = await mongo.system_prompts().find().sort("name", 1).to_list(length=200)
    return [_out(d) for d in docs]


@router.get("/summary", response_model=list[SystemPromptSummary])
async def list_summary(user=Depends(current_user)) -> list[SystemPromptSummary]:
    """Lightweight list for selection UIs."""
    docs = await mongo.system_prompts().find({"active": True}, {"name": 1, "description": 1}).to_list(length=200)
    return [_summary(d) for d in docs]


@router.get("/{prompt_id}", response_model=SystemPromptOut)
async def get_prompt(prompt_id: str, user=Depends(current_user)) -> SystemPromptOut:
    if not await _is_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    doc = await mongo.system_prompts().find_one({"_id": ObjectId(prompt_id)})
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "prompt not found")
    return _out(doc)


@router.post("", response_model=SystemPromptOut, status_code=status.HTTP_201_CREATED)
async def create_prompt(payload: SystemPromptCreate, user=Depends(current_user)) -> SystemPromptOut:
    if not await _is_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    now = datetime.now(tz=UTC)
    doc = {
        "name": payload.name,
        "description": payload.description,
        "tags": payload.tags,
        "active": payload.active,
        "currentVersion": 1,
        "versions": [{"version": 1, "content": payload.content, "changelog": "initial", "createdAt": now}],
        "createdAt": now,
        "updatedAt": now,
    }
    res = await mongo.system_prompts().insert_one(doc)
    doc["_id"] = res.inserted_id
    await log_action(actor_id=str(user["_id"]), action="prompt.create", resource=f"prompt:{res.inserted_id}")
    return _out(doc)


@router.patch("/{prompt_id}", response_model=SystemPromptOut)
async def update_prompt(prompt_id: str, payload: SystemPromptUpdate, user=Depends(current_user)) -> SystemPromptOut:
    if not await _is_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    doc = await mongo.system_prompts().find_one({"_id": ObjectId(prompt_id)})
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "prompt not found")

    updates = payload.model_dump(exclude_none=True)
    changelog = updates.pop("changelog", None)
    new_version = False
    if "content" in updates:
        next_v = doc.get("currentVersion", 1) + 1
        version_entry = {
            "version": next_v,
            "content": updates["content"],
            "changelog": changelog or "edit",
            "createdAt": datetime.now(tz=UTC),
        }
        await mongo.system_prompts().update_one(
            {"_id": doc["_id"]},
            {"$push": {"versions": version_entry}, "$set": {"currentVersion": next_v}},
        )
        new_version = True
    if updates:
        updates["updatedAt"] = datetime.now(tz=UTC)
        await mongo.system_prompts().update_one({"_id": doc["_id"]}, {"$set": updates})
    fresh = await mongo.system_prompts().find_one({"_id": doc["_id"]})
    await log_action(actor_id=str(user["_id"]), action="prompt.update", resource=f"prompt:{prompt_id}", metadata={"newVersion": new_version})
    return _out(fresh)


@router.delete("/{prompt_id}", status_code=204)
async def delete_prompt(prompt_id: str, user=Depends(current_user)) -> None:
    if not await _is_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    res = await mongo.system_prompts().delete_one({"_id": ObjectId(prompt_id)})
    if res.deleted_count == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "prompt not found")
    await log_action(actor_id=str(user["_id"]), action="prompt.delete", resource=f"prompt:{prompt_id}")


@router.get("/{prompt_id}/versions/{version}")
async def get_version(prompt_id: str, version: int, user=Depends(current_user)) -> dict:
    if not await _is_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    doc = await mongo.system_prompts().find_one({"_id": ObjectId(prompt_id)})
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "prompt not found")
    for v in doc.get("versions", []):
        if v["version"] == version:
            return {"version": v["version"], "content": v["content"], "changelog": v.get("changelog"), "createdAt": v["createdAt"]}
    raise HTTPException(status.HTTP_404_NOT_FOUND, "version not found")
