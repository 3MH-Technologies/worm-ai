"""Summarization service. Compresses long chat history into a `summary` memory
slice so the system prompt never grows uncontrollably."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import current_user
from app.db import mongo
from app.services import notrack
from app.services.audit import log_action

log = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


SUMMARIZE_PROMPT = (
    "You compress a chat history into a single concise summary (max 220 words) "
    "that preserves the user's goals, decisions, open questions, named entities, "
    "and any code or file references. Output ONLY the summary. No preamble."
)


@router.post("/conversations/{cid}/summarize", status_code=201)
async def summarize(cid: str, user=Depends(current_user)) -> dict:
    conv = await mongo.conversations().find_one({"_id": ObjectId(cid), "userId": user["_id"]})
    if not conv:
        raise HTTPException(404, "conversation not found")
    msgs = await mongo.messages().find({"conversationId": conv["_id"]}).sort("createdAt", 1).to_list(length=400)
    if len(msgs) < 6:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "conversation too short to summarize")

    history_text = "\n\n".join(
        f"[{m['role']}] {m['content'][:2000]}" for m in msgs[-200:]
    )
    # Fresh notrack chat (no chat_id) so the summary request doesn't pollute the conversation.
    summary, _ = await notrack.get_notrack().complete(f"{SUMMARIZE_PROMPT}\n\n{history_text}")

    now = datetime.now(tz=UTC)
    # remove old summaries for this conversation
    await mongo.memories().delete_many({"userId": user["_id"], "kind": "summary", "source": f"conversation:{cid}"})
    mem_doc = {
        "userId": user["_id"],
        "kind": "summary",
        "content": summary.strip(),
        "weight": 2.0,
        "source": f"conversation:{cid}",
        "createdAt": now,
        "lastUsedAt": None,
    }
    res = await mongo.memories().insert_one(mem_doc)
    await mongo.conversation_summaries().insert_one({
        "conversationId": conv["_id"],
        "userId": user["_id"],
        "summary": summary.strip(),
        "uptoMessageId": msgs[-1]["_id"],
        "createdAt": now,
    })
    await log_action(actor_id=str(user["_id"]), action="chat.summarize", resource=f"conversation:{cid}")
    return {
        "id": str(res.inserted_id),
        "summary": summary.strip(),
        "messages": len(msgs),
        "model": "notrack",
    }
