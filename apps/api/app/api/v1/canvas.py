"""Canvas: documents, code, markdown, project, research workspaces."""

from __future__ import annotations

import difflib
from datetime import UTC, datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import current_user
from app.db import mongo
from app.models.extras import CanvasCreate, CanvasOut, CanvasUpdate, CanvasVersion

router = APIRouter(prefix="/canvas", tags=["canvas"])


def _to_out(doc: dict) -> CanvasOut:
    return CanvasOut(
        id=str(doc["_id"]),
        ownerId=str(doc["ownerId"]),
        title=doc["title"],
        type=doc.get("type", "document"),
        content=doc.get("content", ""),
        metadata=doc.get("metadata") or {},
        conversationId=str(doc["conversationId"]) if doc.get("conversationId") else None,
        currentVersion=doc.get("currentVersion", 1),
        createdAt=doc.get("createdAt") or datetime.now(tz=UTC),
        updatedAt=doc.get("updatedAt") or datetime.now(tz=UTC),
    )


@router.get("", response_model=list[CanvasOut])
async def list_canvas(
    user=Depends(current_user),
    type: str | None = None,
    limit: int = Query(default=50, le=200),
) -> list[CanvasOut]:
    query: dict = {"ownerId": user["_id"]}
    if type:
        query["type"] = type
    docs = await mongo.canvases().find(query).sort("updatedAt", -1).limit(limit).to_list(length=limit)
    return [_to_out(d) for d in docs]


@router.post("", response_model=CanvasOut, status_code=201)
async def create_canvas(payload: CanvasCreate, user=Depends(current_user)) -> CanvasOut:
    now = datetime.now(tz=UTC)
    doc = {
        "ownerId": user["_id"],
        "title": payload.title,
        "type": payload.type,
        "content": payload.content,
        "metadata": payload.metadata,
        "conversationId": ObjectId(payload.conversationId) if payload.conversationId else None,
        "currentVersion": 1,
        "createdAt": now,
        "updatedAt": now,
    }
    res = await mongo.canvases().insert_one(doc)
    doc["_id"] = res.inserted_id
    # initial version snapshot
    await mongo.canvas_versions().insert_one({
        "canvasId": res.inserted_id,
        "version": 1,
        "content": payload.content,
        "commitMessage": payload.metadata.get("initialMessage", "initial"),
        "authorId": user["_id"],
        "createdAt": now,
    })
    return _to_out(doc)


@router.get("/{canvas_id}", response_model=CanvasOut)
async def get_canvas(canvas_id: str, user=Depends(current_user)) -> CanvasOut:
    doc = await mongo.canvases().find_one({"_id": ObjectId(canvas_id), "ownerId": user["_id"]})
    if not doc:
        raise HTTPException(404, "canvas not found")
    return _to_out(doc)


@router.patch("/{canvas_id}", response_model=CanvasOut)
async def update_canvas(canvas_id: str, payload: CanvasUpdate, user=Depends(current_user)) -> CanvasOut:
    canvas = await mongo.canvases().find_one({"_id": ObjectId(canvas_id), "ownerId": user["_id"]})
    if not canvas:
        raise HTTPException(404, "canvas not found")
    updates = payload.model_dump(exclude_none=True)
    commit_message = updates.pop("commitMessage", None) or "edit"
    content_changed = "content" in updates and updates["content"] != canvas.get("content", "")
    if content_changed:
        next_v = (canvas.get("currentVersion") or 1) + 1
        await mongo.canvas_versions().insert_one({
            "canvasId": canvas["_id"],
            "version": next_v,
            "content": updates["content"],
            "commitMessage": commit_message,
            "authorId": user["_id"],
            "createdAt": datetime.now(tz=UTC),
        })
        updates["currentVersion"] = next_v
    updates["updatedAt"] = datetime.now(tz=UTC)
    await mongo.canvases().update_one({"_id": canvas["_id"]}, {"$set": updates})
    return _to_out(await mongo.canvases().find_one({"_id": canvas["_id"]}))


@router.delete("/{canvas_id}", status_code=204)
async def delete_canvas(canvas_id: str, user=Depends(current_user)) -> None:
    res = await mongo.canvases().delete_one({"_id": ObjectId(canvas_id), "ownerId": user["_id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, "canvas not found")
    await mongo.canvas_versions().delete_many({"canvasId": ObjectId(canvas_id)})


@router.get("/{canvas_id}/versions", response_model=list[CanvasVersion])
async def list_versions(canvas_id: str, user=Depends(current_user)) -> list[CanvasVersion]:
    canvas = await mongo.canvases().find_one({"_id": ObjectId(canvas_id), "ownerId": user["_id"]})
    if not canvas:
        raise HTTPException(404, "canvas not found")
    docs = await mongo.canvas_versions().find({"canvasId": canvas["_id"]}).sort("version", -1).limit(100).to_list(length=100)
    return [CanvasVersion(
        version=d["version"], content=d["content"], commitMessage=d.get("commitMessage"),
        authorId=str(d["authorId"]), createdAt=d["createdAt"],
    ) for d in docs]


@router.post("/{canvas_id}/restore/{version}")
async def restore_version(canvas_id: str, version: int, user=Depends(current_user)) -> CanvasOut:
    canvas = await mongo.canvases().find_one({"_id": ObjectId(canvas_id), "ownerId": user["_id"]})
    if not canvas:
        raise HTTPException(404, "canvas not found")
    v = await mongo.canvas_versions().find_one({"canvasId": canvas["_id"], "version": version})
    if not v:
        raise HTTPException(404, "version not found")
    next_v = (canvas.get("currentVersion") or 1) + 1
    await mongo.canvas_versions().insert_one({
        "canvasId": canvas["_id"],
        "version": next_v,
        "content": v["content"],
        "commitMessage": f"restore from v{version}",
        "authorId": user["_id"],
        "createdAt": datetime.now(tz=UTC),
    })
    await mongo.canvases().update_one(
        {"_id": canvas["_id"]},
        {"$set": {"content": v["content"], "currentVersion": next_v, "updatedAt": datetime.now(tz=UTC)}},
    )
    return _to_out(await mongo.canvases().find_one({"_id": canvas["_id"]}))


@router.get("/{canvas_id}/diff/{a}/{b}")
async def diff_versions(canvas_id: str, a: int, b: int, user=Depends(current_user)) -> dict:
    canvas = await mongo.canvases().find_one({"_id": ObjectId(canvas_id), "ownerId": user["_id"]})
    if not canvas:
        raise HTTPException(404, "canvas not found")
    va = await mongo.canvas_versions().find_one({"canvasId": canvas["_id"], "version": a})
    vb = await mongo.canvas_versions().find_one({"canvasId": canvas["_id"], "version": b})
    if not va or not vb:
        raise HTTPException(404, "version not found")
    diff = list(difflib.unified_diff(
        va["content"].splitlines(),
        vb["content"].splitlines(),
        fromfile=f"v{a}", tofile=f"v{b}", lineterm="",
    ))
    return {"a": a, "b": b, "diff": "\n".join(diff)}
