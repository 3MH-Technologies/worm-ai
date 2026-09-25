"""Conversation + message endpoints. Streaming uses SSE."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from app.api.deps import current_user, enforce_approval, rate_limit
from app.core.config import get_settings
from app.db import mongo
from app.models.chat import (
    ConversationCreate,
    ConversationOut,
    ConversationUpdate,
    ConversationWithMessages,
    FolderCreate,
    FolderOut,
    MessageCreate,
    MessageEdit,
    MessageOut,
    MessageReaction,
)
from app.services import notrack

log = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


async def _web_search_for_chat(query: str, max_results: int = 5) -> str:
    """Run a web search and return formatted results for injection into the system prompt."""
    from app.api.v1.web import _ddg_search, _serper_search, _tavily_search
    settings = get_settings()
    provider = settings.web_search_provider
    try:
        if provider == "serper" and settings.serper_api_key:
            results = await _serper_search(query, max_results, settings.serper_api_key)
        elif provider == "tavily" and settings.tavily_api_key:
            results = await _tavily_search(query, max_results, settings.tavily_api_key)
        else:
            results = await _ddg_search(query, max_results)
    except Exception:
        log.exception("web_search_for_chat failed")
        return ""
    if not results:
        return ""
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"[{i}] **{r.title}**\n    URL: {r.url}\n    {r.snippet}")
    return "\n\n".join(lines)


# ---- Folders ----
def _folder_out(doc: dict, count: int = 0) -> FolderOut:
    return FolderOut(
        id=str(doc["_id"]),
        userId=str(doc["userId"]),
        name=doc["name"],
        color=doc.get("color"),
        icon=doc.get("icon"),
        conversationCount=count,
    )


@router.get("/folders", response_model=list[FolderOut])
async def list_folders(user=Depends(current_user)) -> list[FolderOut]:
    folders = await mongo.folders().find({"userId": user["_id"]}).sort("name", 1).to_list(length=200)
    out = []
    for f in folders:
        cnt = await mongo.conversations().count_documents({"userId": user["_id"], "folderId": f["_id"]})
        out.append(_folder_out(f, cnt))
    return out


@router.post("/folders", response_model=FolderOut, status_code=201)
async def create_folder(payload: FolderCreate, user=Depends(current_user)) -> FolderOut:
    doc = {
        "userId": user["_id"],
        "name": payload.name,
        "color": payload.color,
        "icon": payload.icon,
        "createdAt": datetime.now(tz=UTC),
    }
    res = await mongo.folders().insert_one(doc)
    doc["_id"] = res.inserted_id
    return _folder_out(doc)


@router.delete("/folders/{folder_id}", status_code=204)
async def delete_folder(folder_id: str, user=Depends(current_user)) -> None:
    await mongo.folders().delete_one({"_id": ObjectId(folder_id), "userId": user["_id"]})
    await mongo.conversations().update_many(
        {"userId": user["_id"], "folderId": ObjectId(folder_id)},
        {"$unset": {"folderId": ""}},
    )


# ---- Conversations ----
def _conv_out(doc: dict, msg_count: int = 0) -> ConversationOut:
    return ConversationOut(
        id=str(doc["_id"]),
        userId=str(doc["userId"]),
        title=doc.get("title") or "New chat",
        modelId=str(doc["modelId"]) if doc.get("modelId") else None,
        mode=doc.get("mode", "chat"),
        folderId=str(doc["folderId"]) if doc.get("folderId") else None,
        favorite=doc.get("favorite", False),
        shared=doc.get("shared", False),
        messageCount=msg_count,
        lastMessageAt=doc.get("lastMessageAt"),
        createdAt=doc.get("createdAt") or datetime.now(tz=UTC),
        updatedAt=doc.get("updatedAt") or datetime.now(tz=UTC),
    )


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    user=Depends(current_user),
    q: str | None = None,
    folderId: str | None = None,
    favorite: bool | None = None,
    shared: bool | None = None,
    limit: int = Query(default=100, le=200),
) -> list[ConversationOut]:
    query: dict[str, Any] = {"userId": user["_id"]}
    if folderId:
        query["folderId"] = ObjectId(folderId)
    if favorite is not None:
        query["favorite"] = favorite
    if shared is not None:
        query["shared"] = shared
    if q:
        query["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
        ]
    docs = await mongo.conversations().find(query).sort("updatedAt", -1).limit(limit).to_list(length=limit)
    return [_conv_out(d) for d in docs]


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(payload: ConversationCreate, user=Depends(current_user)) -> ConversationOut:
    await enforce_approval(user)
    now = datetime.now(tz=UTC)
    model_id = (payload.modelId or "").strip()
    if len(model_id) == 1:
        model_id = model_id.upper()  # notrack single-letter codes
    doc = {
        "userId": user["_id"],
        "title": payload.title or "New chat",
        "modelId": model_id or None,
        "mode": payload.mode,
        "folderId": ObjectId(payload.folderId) if payload.folderId else None,
        "favorite": False,
        "shared": False,
        "createdAt": now,
        "updatedAt": now,
        "lastMessageAt": None,
    }
    res = await mongo.conversations().insert_one(doc)
    doc["_id"] = res.inserted_id
    return _conv_out(doc)


@router.get("/conversations/{cid}", response_model=ConversationWithMessages)
async def get_conversation(cid: str, user=Depends(current_user), limit: int = Query(default=200, le=500)) -> ConversationWithMessages:
    conv = await mongo.conversations().find_one({"_id": ObjectId(cid), "userId": user["_id"]})
    if not conv:
        raise HTTPException(404, "conversation not found")
    msgs = await mongo.messages().find({"conversationId": conv["_id"]}).sort("createdAt", 1).limit(limit).to_list(length=limit)
    msg_count = await mongo.messages().count_documents({"conversationId": conv["_id"]})
    base = _conv_out(conv, msg_count)
    return ConversationWithMessages(
        **base.model_dump(),
        messages=[MessageOut(
            id=str(m["_id"]),
            conversationId=str(m["conversationId"]),
            role=m["role"],
            content=m["content"],
            tokens=m.get("tokens"),
            model=m.get("model"),
            metadata=m.get("metadata") or {},
            reaction=m.get("reaction"),
            parentId=str(m["parentId"]) if m.get("parentId") else None,
            createdAt=m["createdAt"],
            editedAt=m.get("editedAt"),
        ) for m in msgs],
    )


@router.patch("/conversations/{cid}", response_model=ConversationOut)
async def update_conversation(cid: str, payload: ConversationUpdate, user=Depends(current_user)) -> ConversationOut:
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        conv = await mongo.conversations().find_one({"_id": ObjectId(cid), "userId": user["_id"]})
        if not conv:
            raise HTTPException(404, "not found")
        return _conv_out(conv)
    updates["updatedAt"] = datetime.now(tz=UTC)
    res = await mongo.conversations().update_one(
        {"_id": ObjectId(cid), "userId": user["_id"]},
        {"$set": updates},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "not found")
    conv = await mongo.conversations().find_one({"_id": ObjectId(cid)})
    return _conv_out(conv)


@router.delete("/conversations/{cid}", status_code=204)
async def delete_conversation(cid: str, user=Depends(current_user)) -> None:
    res = await mongo.conversations().delete_one({"_id": ObjectId(cid), "userId": user["_id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, "not found")
    await mongo.messages().delete_many({"conversationId": ObjectId(cid)})


# ---- Messages ----
@router.post("/conversations/{cid}/messages", response_model=MessageOut)
async def post_message(cid: str, payload: MessageCreate, user=Depends(current_user), _: None = Depends(rate_limit)) -> MessageOut:
    """Non-streaming message send. Returns the saved user message; assistant reply
    can be fetched via /stream. Prefer /stream for chat UX."""
    await enforce_approval(user)
    if not payload.content.strip():
        raise HTTPException(400, "message content is required")
    conv = await mongo.conversations().find_one({"_id": ObjectId(cid), "userId": user["_id"]})
    if not conv:
        raise HTTPException(404, "conversation not found")

    now = datetime.now(tz=UTC)
    doc = {
        "conversationId": conv["_id"],
        "userId": user["_id"],
        "role": payload.role,
        "content": payload.content,
        "tokens": None,
        "model": None,
        "metadata": {"attachments": payload.attachments or []},
        "parentId": ObjectId(payload.parentId) if payload.parentId else None,
        "createdAt": now,
    }
    res = await mongo.messages().insert_one(doc)
    doc["_id"] = res.inserted_id
    await mongo.conversations().update_one(
        {"_id": conv["_id"]},
        {"$set": {"updatedAt": now, "lastMessageAt": now},
         "$setOnInsert": {"createdAt": conv.get("createdAt", now)}},
    )
    if not conv.get("title") or conv.get("title") == "New chat":
        await mongo.conversations().update_one(
            {"_id": conv["_id"]},
            {"$set": {"title": payload.content[:48] + ("…" if len(payload.content) > 48 else "")}},
        )
    return MessageOut(
        id=str(doc["_id"]), conversationId=str(conv["_id"]), role=doc["role"], content=doc["content"],
        tokens=doc.get("tokens"), model=doc.get("model"), metadata=doc.get("metadata") or {},
        reaction=None, parentId=payload.parentId, createdAt=now,
    )


@router.patch("/conversations/{cid}/messages/{mid}", response_model=MessageOut)
async def edit_message(cid: str, mid: str, payload: MessageEdit, user=Depends(current_user)) -> MessageOut:
    res = await mongo.messages().find_one_and_update(
        {"_id": ObjectId(mid), "conversationId": ObjectId(cid), "userId": user["_id"]},
        {"$set": {"content": payload.content, "editedAt": datetime.now(tz=UTC)}},
        return_document=True,
    )
    if not res:
        raise HTTPException(404, "message not found")
    return MessageOut(
        id=str(res["_id"]), conversationId=str(res["conversationId"]), role=res["role"], content=res["content"],
        tokens=res.get("tokens"), model=res.get("model"), metadata=res.get("metadata") or {},
        reaction=res.get("reaction"), parentId=str(res["parentId"]) if res.get("parentId") else None,
        createdAt=res["createdAt"], editedAt=res.get("editedAt"),
    )


@router.delete("/conversations/{cid}/messages/{mid}", status_code=204)
async def delete_message(cid: str, mid: str, user=Depends(current_user)) -> None:
    res = await mongo.messages().delete_one({
        "_id": ObjectId(mid), "conversationId": ObjectId(cid), "userId": user["_id"],
    })
    if res.deleted_count == 0:
        raise HTTPException(404, "message not found")


@router.post("/conversations/{cid}/messages/{mid}/react", response_model=MessageOut)
async def react_message(cid: str, mid: str, payload: MessageReaction, user=Depends(current_user)) -> MessageOut:
    # Verify the message belongs to one of the current user's conversations
    conv = await mongo.conversations().find_one({"_id": ObjectId(cid), "userId": user["_id"]})
    if not conv:
        raise HTTPException(404, "conversation not found")
    res = await mongo.messages().find_one_and_update(
        {"_id": ObjectId(mid), "conversationId": ObjectId(cid)},
        {"$set": {"reaction": payload.reaction}},
        return_document=True,
    )
    if not res:
        raise HTTPException(404, "message not found")
    return MessageOut(
        id=str(res["_id"]), conversationId=str(res["conversationId"]), role=res["role"], content=res["content"],
        tokens=res.get("tokens"), model=res.get("model"), metadata=res.get("metadata") or {},
        reaction=res.get("reaction"), parentId=str(res["parentId"]) if res.get("parentId") else None,
        createdAt=res["createdAt"], editedAt=res.get("editedAt"),
    )


# ---- Streaming (internal chat backend) ----
# Inline image attachments are shipped to the model as data URLs; text files are
# skipped (the upstream dispatch only understands image payloads).
_ATTACHMENT_MAX_COUNT = 4
_ATTACHMENT_MAX_EACH = 8 * 1024 * 1024
_ATTACHMENT_MAX_TOTAL = 16 * 1024 * 1024


async def _model_attachments(
    items: list[dict[str, Any]] | None, user_id: ObjectId
) -> list[str]:
    import base64

    from app.api.v1.attachments import _storage_dir

    out: list[str] = []
    total = 0
    for item in items or []:
        if len(out) >= _ATTACHMENT_MAX_COUNT:
            break
        att_id = item.get("id") if isinstance(item, dict) else None
        if not att_id or not ObjectId.is_valid(str(att_id)):
            continue
        doc = await mongo.attachments().find_one({"_id": ObjectId(str(att_id)), "userId": user_id})
        if not doc:
            continue
        mime = str(doc.get("mimeType") or "")
        if not mime.startswith("image/"):
            continue
        size = int(doc.get("size") or 0)
        if size > _ATTACHMENT_MAX_EACH or total + size > _ATTACHMENT_MAX_TOTAL:
            log.warning("skipping oversized attachment id=%s size=%s", att_id, size)
            continue
        path = _storage_dir() / doc.get("storageKey", "")
        if not path.exists():
            continue
        try:
            raw = await asyncio.to_thread(path.read_bytes)
        except OSError as e:
            log.warning("attachment read failed id=%s err=%s", att_id, e)
            continue
        out.append(f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}")
        total += size
    return out


def _resolve_model_code(conv: dict, requested_model_id: str | None) -> str:
    """Resolve the notrack model code (A/B/C/F) for this turn."""
    settings = get_settings()
    code = str(requested_model_id or conv.get("modelId") or settings.notrack_model or "C").strip().upper()
    if code not in notrack.NOTRACK_MODELS:
        code = settings.notrack_model if settings.notrack_model in notrack.NOTRACK_MODELS else "C"
    return code


@router.post("/conversations/{cid}/stream")
async def stream_message(
    cid: str,
    payload: MessageCreate,
    request: Request,
    background: BackgroundTasks,
    user=Depends(current_user),
    _: None = Depends(rate_limit),
) -> EventSourceResponse:
    await enforce_approval(user)
    conv = await mongo.conversations().find_one({"_id": ObjectId(cid), "userId": user["_id"]})
    if not conv:
        raise HTTPException(404, "conversation not found")

    settings = get_settings()
    model_code = _resolve_model_code(conv, payload.modelId)
    model_name = notrack.NOTRACK_MODELS[model_code]
    regenerate = bool(payload.regenerate)
    content = (payload.content or "").strip()
    if not regenerate and not content:
        raise HTTPException(400, "message content is required")
    if len(content) > notrack.MAX_USER_INPUT:
        raise HTTPException(
            400,
            f"Message is too long ({len(content)} characters). "
            f"The limit is {notrack.MAX_USER_INPUT} — try splitting it or attaching a file.",
        )

    now = datetime.now(tz=UTC)
    user_msg_id: ObjectId | None = None
    if not regenerate:
        # Persist user message
        user_msg_doc = {
            "conversationId": conv["_id"],
            "userId": user["_id"],
            "role": "user",
            "content": content,
            "tokens": None,
            "model": None,
            "metadata": {"attachments": payload.attachments or []},
            "parentId": ObjectId(payload.parentId) if payload.parentId else None,
            "createdAt": now,
        }
        user_msg_res = await mongo.messages().insert_one(user_msg_doc)
        user_msg_id = user_msg_res.inserted_id

        # Update conversation meta
        title_update: dict[str, Any] = {"modelId": model_code}
        if conv.get("title") in (None, "New chat"):
            title_update["title"] = content[:48] + ("…" if len(content) > 48 else "")
        await mongo.conversations().update_one(
            {"_id": conv["_id"]},
            {"$set": {"updatedAt": now, "lastMessageAt": now, **title_update}},
        )
    else:
        # Regenerating: drop the previous assistant reply locally so the UI replaces it.
        last_assistant = await mongo.messages().find_one(
            {"conversationId": conv["_id"], "role": "assistant"}, sort=[("createdAt", -1)]
        )
        if last_assistant:
            await mongo.messages().delete_one({"_id": last_assistant["_id"]})

    # Server-side context lives in the notrack chat; its id is kept on the conversation.
    nt_chat_id: str | None = conv.get("notrackChatId")

    content_to_send = content
    if payload.webSearch and content:
        search_text = await _web_search_for_chat(content)
        if search_text:
            content_to_send = f"{content}\n\n## Current Web Search Results\n\n{search_text}"
    # Web results are appended after the length check, so re-cap here — the
    # upstream rejects anything past MAX_USER_INPUT outright.
    content_to_send = content_to_send[: notrack.MAX_USER_INPUT]

    # Ship the turn's image attachments to the model (data URLs); only when the
    # caller supplied them — regenerate replays the upstream chat instead.
    model_attachments = await _model_attachments(payload.attachments, user["_id"])

    client = notrack.get_notrack()

    async def event_gen():
        nonlocal nt_chat_id
        buffer: list[str] = []
        start = time.perf_counter()
        first_token_at: float | None = None
        finish_reason: str | None = None
        assistant_id: ObjectId | None = None
        try:
            yield {"event": "start", "data": json.dumps({
                "userMessageId": str(user_msg_id) if user_msg_id else None,
                "model": model_name,
                "provider": "internal",
            })}
            async for ev in client.stream_dispatch(
                content_to_send,
                chat_id=nt_chat_id,
                model=model_code,
                persona=settings.notrack_persona,
                max_turns=settings.notrack_max_turns,
                attachments=model_attachments or None,
                regenerate=regenerate,
            ):
                if await request.is_disconnected():
                    break
                et = ev["type"]
                if et == "chat_meta":
                    new_chat_id = ev.get("chat_id")
                    if new_chat_id and new_chat_id != nt_chat_id:
                        nt_chat_id = new_chat_id
                        await mongo.conversations().update_one(
                            {"_id": conv["_id"]}, {"$set": {"notrackChatId": new_chat_id}}
                        )
                elif et == "delta":
                    text = ev["text"]
                    if first_token_at is None:
                        first_token_at = time.perf_counter()
                    buffer.append(text)
                    yield {"event": "delta", "data": json.dumps({"text": text})}
                elif et == "turn_end":
                    # Separate multi-speaker turns (Synthesis mode) visually.
                    if buffer and not "".join(buffer).endswith("\n\n"):
                        buffer.append("\n\n")
                        yield {"event": "delta", "data": json.dumps({"text": "\n\n"})}
                elif et == "error":
                    finish_reason = "error"
                    yield {"event": "error", "data": json.dumps({"message": ev.get("message") or "upstream error"})}
            if finish_reason is None:
                finish_reason = "stop"
                yield {"event": "finish", "data": json.dumps({"reason": "stop"})}
        except asyncio.CancelledError:
            finish_reason = "cancelled"
        except Exception as e:
            log.exception("stream error: %s", e)
            finish_reason = "error"
            yield {"event": "error", "data": json.dumps({"message": str(e)})}
        finally:
            full = "".join(buffer).strip()
            now2 = datetime.now(tz=UTC)
            # A failed stream must not persist "[Error: …]" or an empty assistant
            # turn — only real output becomes a message.
            assistant_id: ObjectId | None = None
            if full:
                assistant_doc = {
                    "conversationId": conv["_id"],
                    "userId": user["_id"],
                    "role": "assistant",
                    "content": full,
                    "tokens": notrack.count_tokens(full),
                    "model": model_name,
                    "metadata": {
                        "latency_ms": int((time.perf_counter() - start) * 1000),
                        "ttft_ms": int(((first_token_at or time.perf_counter()) - start) * 1000),
                        "finish_reason": finish_reason,
                        "provider": "internal",
                    },
                    "parentId": user_msg_id,
                    "createdAt": now2,
                }
                res = await mongo.messages().insert_one(assistant_doc)
                assistant_id = res.inserted_id

            # Save as Canvas if requested
            canvas_id: ObjectId | None = None
            if payload.canvas and full.strip():
                canvas_title = conv.get("title") or payload.content[:48] + "…"
                canvas_doc = {
                    "ownerId": user["_id"],
                    "title": canvas_title,
                    "type": "document",
                    "content": full,
                    "metadata": {"source": "chat", "conversationId": str(conv["_id"]), "model": model_name, "provider": "internal"},
                    "conversationId": conv["_id"],
                    "currentVersion": 1,
                    "createdAt": now2,
                    "updatedAt": now2,
                }
                canvas_res = await mongo.canvases().insert_one(canvas_doc)
                canvas_id = canvas_res.inserted_id
                await mongo.canvas_versions().insert_one({
                    "canvasId": canvas_id,
                    "version": 1,
                    "content": full,
                    "commitMessage": "Chat response",
                    "authorId": user["_id"],
                    "createdAt": now2,
                })

            done_data: dict[str, Any] = {
                "assistantMessageId": str(assistant_id) if assistant_id else None,
                "tokens": assistant_doc["tokens"] if full else 0,
                "latency_ms": int((time.perf_counter() - start) * 1000),
                "ttft_ms": int(((first_token_at or time.perf_counter()) - start) * 1000),
            }
            if canvas_id:
                done_data["canvasId"] = str(canvas_id)
            yield {"event": "done", "data": json.dumps(done_data)}
            if full:
                background.add_task(_track_usage, user["_id"], notrack.count_tokens(full), "internal")

    return EventSourceResponse(event_gen())


async def _track_usage(user_id: ObjectId, tokens: int, provider: str) -> None:
    from datetime import datetime

    from app.cache.redis import client as redis_client
    today = datetime.utcnow().strftime("%Y-%m-%d")
    key = f"usage:{today}:{provider}"
    try:
        await redis_client().incrby(key, tokens)
        await redis_client().expire(key, 60 * 60 * 24 * 60)
    except Exception:
        log.exception("track_usage failed")
