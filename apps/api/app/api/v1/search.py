"""Full-text search across conversations, messages, users, models, canvas, memory."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Query

from app.api.deps import current_user
from app.db import mongo
from app.models.extras import SearchHit, SearchResponse
from app.services.notrack import NOTRACK_MODEL_DESCRIPTIONS, NOTRACK_MODELS

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(min_length=1, max_length=200),
    kinds: str | None = Query(default=None, description="Comma-separated: conversation,message,user,model,canvas,memory"),
    user=Depends(current_user),
    limit: int = Query(default=20, le=50),
) -> SearchResponse:
    started = time.perf_counter()
    requested = set(kinds.split(",")) if kinds else {"conversation", "message", "model", "canvas", "memory"}
    hits: list[SearchHit] = []

    async def push(kind: str, id_: str, title: str, snippet: str, score: float, **extra):
        hits.append(SearchHit(kind=kind, id=id_, title=title, snippet=snippet, score=score, extra=extra))

    # conversations
    if "conversation" in requested:
        cursor = mongo.conversations().find(
            {"userId": user["_id"], "$text": {"$search": q}},
            {"score": {"$meta": "textScore"}, "title": 1, "userId": 1},
        ).sort([("score", {"$meta": "textScore"})]).limit(limit)
        async for d in cursor:
            await push("conversation", str(d["_id"]), d.get("title") or "Chat", (d.get("title") or "")[:200], float(d.get("score") or 0))

    # messages
    if "message" in requested:
        cursor = mongo.messages().find(
            {"userId": user["_id"], "$text": {"$search": q}},
            {"score": {"$meta": "textScore"}, "content": 1, "role": 1, "conversationId": 1},
        ).sort([("score", {"$meta": "textScore"})]).limit(limit)
        async for d in cursor:
            await push("message", str(d["_id"]), f"{d['role'].title()} message", d["content"][:240], float(d.get("score") or 0), conversationId=str(d["conversationId"]))

    # models — the catalogue is static (see app/api/v1/models.py), so match it
    # in-process instead of running a $text query that would need a Mongo text
    # index that no longer exists.
    if "model" in requested:
        needle = q.lower()
        for code, name in NOTRACK_MODELS.items():
            desc = NOTRACK_MODEL_DESCRIPTIONS.get(code) or ""
            hay = f"{code} {name} {desc}".lower()
            if needle in hay:
                score = 1.0 if needle in name.lower() else 0.6
                await push("model", code, name, desc[:200], score)

    # canvas
    if "canvas" in requested:
        cursor = mongo.canvases().find(
            {"ownerId": user["_id"], "$or": [
                {"title": {"$regex": q, "$options": "i"}},
                {"content": {"$regex": q, "$options": "i"}},
            ]},
            {"title": 1, "content": 1, "type": 1},
        ).limit(limit)
        async for d in cursor:
            await push("canvas", str(d["_id"]), d.get("title") or "Canvas", (d.get("content") or "")[:200], 0.5, type=d.get("type"))

    # memory
    if "memory" in requested:
        cursor = mongo.memories().find(
            {"userId": user["_id"], "content": {"$regex": q, "$options": "i"}},
            {"content": 1, "kind": 1},
        ).limit(limit)
        async for d in cursor:
            await push("memory", str(d["_id"]), f"Memory: {d.get('kind', 'long_term')}", d["content"][:200], 0.4)

    hits.sort(key=lambda h: h.score, reverse=True)
    return SearchResponse(query=q, hits=hits[:limit], took_ms=int((time.perf_counter() - started) * 1000))
