"""Worm Agent — the coding agent behind /agent.

BY 3MH TECHNOLOGIES | https://3mh.pages.dev | t.me/j49_c

How it works: we hand the model a handful of tools (workspace files + web),
let it call them in a loop, and stream every step back to the browser.
Workspace files are stored as versioned canvases scoped to the owner and the
conversation — nothing leaks between users and every edit stays reversible.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app.api.deps import current_user, enforce_approval, rate_limit
from app.core.config import get_settings
from app.db import mongo
from app.models.chat import MessageCreate
from app.services import deepseek

log = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])

AGENT_SYSTEM_PROMPT = (
    "You are Worm Agent, an autonomous coding agent by 3MH Technologies (site: worm-ai). "
    "You build software inside the user's persistent workspace.\n\n"
    "Tools available:\n"
    "- create_file(path, content, language?) — create or overwrite a workspace file (code, docs, configs)\n"
    "- read_file(path) — read a workspace file\n"
    "- list_files() — list workspace files\n"
    "- delete_file(path) — delete a workspace file\n"
    "- web_search(query) — search the web for current information\n"
    "- fetch_url(url) — fetch a web page and return its text\n\n"
    "Guidelines:\n"
    "- For code tasks: write COMPLETE, runnable files with create_file using real relative paths (e.g. src/main.py, index.html).\n"
    "- After creating or editing files, briefly summarize the changes and list the file paths.\n"
    "- Use web_search / fetch_url when you need current facts, APIs, or documentation.\n"
    "- Be concise, use markdown formatting, and reply in the user's language.\n"
    "- You are powered by worm-ai internal models."
)

_EXT_TYPES = {
    ".py": "code", ".js": "code", ".ts": "code", ".tsx": "code", ".jsx": "code",
    ".html": "code", ".css": "code", ".json": "code", ".yml": "code", ".yaml": "code",
    ".sh": "code", ".sql": "code", ".go": "code", ".rs": "code", ".java": "code",
    ".c": "code", ".cpp": "code", ".h": "code", ".php": "code", ".rb": "code",
    ".md": "markdown", ".txt": "document",
}


def _file_type(path: str, language: str | None) -> str:
    if language:
        return "markdown" if language.lower() == "markdown" else "code"
    for ext, t in _EXT_TYPES.items():
        if path.lower().endswith(ext):
            return t
    return "document"


TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Create or overwrite a file in the user's persistent workspace. Use for all code, documents and configs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path, e.g. src/main.py"},
                    "content": {"type": "string", "description": "Full file content"},
                    "language": {"type": "string", "description": "Optional language hint, e.g. python"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the workspace by its path.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List all files in the workspace with sizes and update times.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file from the workspace by its path.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web and return the top results.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch a web page and return its text content.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
]

_MAX_FILE_CHARS = 400_000


async def _tool_create_file(user: dict, conv_id: ObjectId, args: dict) -> tuple[str, dict]:
    path = str(args.get("path") or "").strip().lstrip("/")
    content = str(args.get("content") or "")
    language = args.get("language")
    if not path:
        raise ValueError("path is required")
    if len(content) > _MAX_FILE_CHARS:
        raise ValueError(f"content too large (max {_MAX_FILE_CHARS} chars)")
    now = datetime.now(tz=UTC)
    col = mongo.canvases()
    ctype = _file_type(path, language)
    existing = await col.find_one({"ownerId": user["_id"], "conversationId": conv_id, "agentPath": path})
    if existing:
        version = int(existing.get("currentVersion", 1)) + 1
        await col.update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "content": content,
                "type": ctype,
                "currentVersion": version,
                "metadata": {**(existing.get("metadata") or {}), "language": language, "agent": True},
                "updatedAt": now,
            }},
        )
        await mongo.canvas_versions().insert_one({
            "canvasId": existing["_id"], "version": version, "content": content,
            "commitMessage": "Worm Agent update", "authorId": user["_id"], "createdAt": now,
        })
        summary = f"Updated {path} (v{version}, {len(content)} chars)"
        return summary, {"ok": True, "summary": summary, "path": path, "action": "update", "version": version}
    doc = {
        "ownerId": user["_id"],
        "title": path,
        "type": ctype,
        "content": content,
        "metadata": {"language": language, "agent": True, "path": path},
        "conversationId": conv_id,
        "agentPath": path,
        "currentVersion": 1,
        "createdAt": now,
        "updatedAt": now,
    }
    res = await col.insert_one(doc)
    await mongo.canvas_versions().insert_one({
        "canvasId": res.inserted_id, "version": 1, "content": content,
        "commitMessage": "Worm Agent create", "authorId": user["_id"], "createdAt": now,
    })
    summary = f"Created {path} ({len(content)} chars)"
    return summary, {"ok": True, "summary": summary, "path": path, "action": "create", "version": 1}


async def _tool_read_file(user: dict, conv_id: ObjectId, args: dict) -> tuple[str, dict]:
    path = str(args.get("path") or "").strip().lstrip("/")
    if not path:
        raise ValueError("path is required")
    doc = await mongo.canvases().find_one({"ownerId": user["_id"], "conversationId": conv_id, "agentPath": path})
    if not doc:
        summary = f"File not found: {path}"
        return summary, {"ok": False, "summary": summary, "path": path}
    content = (doc.get("content") or "")[:20_000]
    summary = f"Read {path} ({len(content)} chars)"
    return content, {"ok": True, "summary": summary, "path": path}


async def _tool_list_files(user: dict, conv_id: ObjectId, args: dict) -> tuple[str, dict]:
    docs = await mongo.canvases().find(
        {"ownerId": user["_id"], "conversationId": conv_id, "agentPath": {"$exists": True}},
        {"agentPath": 1, "updatedAt": 1, "content": 1, "currentVersion": 1},
    ).sort("agentPath", 1).to_list(length=500)
    if not docs:
        summary = "Workspace is empty"
        return summary, {"ok": True, "summary": summary, "count": 0}
    lines = [
        f"- {d['agentPath']} (v{d.get('currentVersion', 1)}, {len(d.get('content') or '')} chars)"
        for d in docs
    ]
    summary = f"{len(docs)} files: " + ", ".join(d["agentPath"] for d in docs[:5])
    return "\n".join(lines), {"ok": True, "summary": summary, "count": len(docs)}


async def _tool_delete_file(user: dict, conv_id: ObjectId, args: dict) -> tuple[str, dict]:
    path = str(args.get("path") or "").strip().lstrip("/")
    if not path:
        raise ValueError("path is required")
    res = await mongo.canvases().delete_one({"ownerId": user["_id"], "conversationId": conv_id, "agentPath": path})
    if res.deleted_count == 0:
        summary = f"File not found: {path}"
        return summary, {"ok": False, "summary": summary, "path": path}
    summary = f"Deleted {path}"
    return summary, {"ok": True, "summary": summary, "path": path}


async def _tool_web_search(user: dict, conv_id: ObjectId, args: dict) -> tuple[str, dict]:
    query = str(args.get("query") or "").strip()
    if not query:
        raise ValueError("query is required")
    from app.api.v1.web import _ddg_search, _serper_search, _tavily_search
    s = get_settings()
    if s.web_search_provider == "serper" and s.serper_api_key:
        results = await _serper_search(query, 5, s.serper_api_key)
    elif s.web_search_provider == "tavily" and s.tavily_api_key:
        results = await _tavily_search(query, 5, s.tavily_api_key)
    else:
        results = await _ddg_search(query, 5)
    if not results:
        summary = "No results"
        return summary, {"ok": True, "summary": summary, "count": 0}
    text = "\n\n".join(f"[{i}] {r.title}\n{r.url}\n{r.snippet}" for i, r in enumerate(results, 1))
    summary = f"{len(results)} results — {results[0].title}"
    return text[:6000], {"ok": True, "summary": summary, "count": len(results)}


async def _tool_fetch_url(user: dict, conv_id: ObjectId, args: dict) -> tuple[str, dict]:
    url = str(args.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("url must start with http:// or https://")
    from app.api.v1.web import _fetch_content
    text = await _fetch_content(url)
    if not text:
        summary = f"Could not fetch {url}"
        return summary, {"ok": False, "summary": summary}
    summary = f"Fetched {url} ({len(text)} chars)"
    return text[:6000], {"ok": True, "summary": summary}


async def _execute_tool(name: str, args: dict, user: dict, conv_id: ObjectId) -> tuple[str, dict]:
    try:
        if name == "create_file":
            return await _tool_create_file(user, conv_id, args)
        if name == "read_file":
            return await _tool_read_file(user, conv_id, args)
        if name == "list_files":
            return await _tool_list_files(user, conv_id, args)
        if name == "delete_file":
            return await _tool_delete_file(user, conv_id, args)
        if name == "web_search":
            return await _tool_web_search(user, conv_id, args)
        if name == "fetch_url":
            return await _tool_fetch_url(user, conv_id, args)
        return f"Unknown tool: {name}", {"ok": False, "summary": f"Unknown tool: {name}"}
    except Exception as e:
        log.warning("agent tool %s failed: %s", name, e)
        summary = f"Tool error: {type(e).__name__}: {e}"
        return summary, {"ok": False, "summary": summary}


# ---- Endpoints ----
@router.get("/models")
async def agent_models() -> list[dict[str, Any]]:
    """Models exposed for the Worm Agent mode."""
    configured = deepseek.DeepSeekClient.configured()
    return [
        {
            "id": mid,
            "name": m["name"],
            "description": m["description"],
            "provider": "internal",
            "enabled": True,
            "configured": configured,
        }
        for mid, m in deepseek.AGENT_MODELS.items()
    ]


@router.get("/status")
async def agent_status() -> dict[str, Any]:
    """Whether the agent backend (model token) is configured."""
    return {
        "configured": deepseek.DeepSeekClient.configured(),
        "models": list(deepseek.AGENT_MODELS.keys()),
        "provider": "internal",
    }


def _count_tokens(text: str) -> int:
    return max(1, len(text) // 4)


@router.post("/conversations/{cid}/stream")
async def agent_stream(
    cid: str,
    payload: MessageCreate,
    request: Request,
    user=Depends(current_user),
    _: None = Depends(rate_limit),
) -> EventSourceResponse:
    """Run the Worm Agent tool loop and stream progress over SSE.

    Events: start, thinking, delta, tool, tool_result, done, error
    """
    await enforce_approval(user)
    if not deepseek.DeepSeekClient.configured():
        raise HTTPException(
            400,
            "Agent not configured: set DEEPSEEK_TOKEN on the server (see /api/v1/agent/status)",
        )
    conv = await mongo.conversations().find_one({"_id": ObjectId(cid), "userId": user["_id"]})
    if not conv:
        raise HTTPException(404, "conversation not found")

    settings = get_settings()
    requested = (payload.modelId or conv.get("modelId") or settings.deepseek_model or "").strip()
    model = requested if requested in deepseek.AGENT_MODELS else settings.deepseek_model
    if model not in deepseek.AGENT_MODELS:
        model = "deepseek-chat"
    model_name = deepseek.AGENT_MODELS[model]["name"]

    regenerate = bool(payload.regenerate)
    content = (payload.content or "").strip()
    now = datetime.now(tz=UTC)

    if regenerate:
        last_user = await mongo.messages().find_one(
            {"conversationId": conv["_id"], "role": "user"}, sort=[("createdAt", -1)]
        )
        if not last_user:
            raise HTTPException(400, "nothing to regenerate")
        content = last_user["content"]
        last_assistant = await mongo.messages().find_one(
            {"conversationId": conv["_id"], "role": "assistant"}, sort=[("createdAt", -1)]
        )
        if last_assistant:
            await mongo.messages().delete_one({"_id": last_assistant["_id"]})
    else:
        if not content:
            raise HTTPException(400, "message content is required")
        await mongo.messages().insert_one({
            "conversationId": conv["_id"],
            "userId": user["_id"],
            "role": "user",
            "content": content,
            "tokens": None,
            "model": None,
            "metadata": {},
            "parentId": None,
            "createdAt": now,
        })
        title_update: dict[str, Any] = {"modelId": model, "mode": "agent"}
        if conv.get("title") in (None, "New chat"):
            title_update["title"] = content[:48] + ("…" if len(content) > 48 else "")
        await mongo.conversations().update_one(
            {"_id": conv["_id"]},
            {"$set": {"updatedAt": now, "lastMessageAt": now, **title_update}},
        )

    # Build the model history (system + prior turns).
    history_docs = await mongo.messages().find(
        {"conversationId": conv["_id"]}
    ).sort("createdAt", 1).to_list(length=200)
    messages: list[dict[str, Any]] = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
    for m in history_docs:
        if m["role"] in ("user", "assistant") and (m.get("content") or "").strip():
            messages.append({"role": m["role"], "content": m["content"]})

    client = deepseek.get_deepseek()

    async def event_gen():
        buffer: list[str] = []
        tools_used: list[dict[str, Any]] = []
        start = time.perf_counter()
        first_token_at: float | None = None
        iterations = 0
        finish_reason = "stop"
        try:
            yield {"event": "start", "data": json.dumps({
                "model": model_name,
                "provider": "internal",
            })}
            for _ in range(settings.agent_max_iterations):
                iterations += 1
                tool_calls: dict[int, dict[str, Any]] = {}
                turn_text: list[str] = []
                async for ev in client.stream_chat(messages, model=model, tools=TOOLS):
                    if await request.is_disconnected():
                        break
                    et = ev["type"]
                    if et == "tool_call_delta":
                        idx = int(ev.get("index") or 0)
                        call = tool_calls.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                        if ev.get("id"):
                            call["id"] = call["id"] or ev["id"]
                        if ev.get("name"):
                            call["name"] = ev["name"]
                        call["arguments"] += ev.get("arguments") or ""
                    elif et == "reasoning":
                        yield {"event": "thinking", "data": json.dumps({"text": ev["text"]})}
                    elif et == "text":
                        if first_token_at is None:
                            first_token_at = time.perf_counter()
                        turn_text.append(ev["text"])
                        buffer.append(ev["text"])
                        yield {"event": "delta", "data": json.dumps({"text": ev["text"]})}

                if await request.is_disconnected():
                    finish_reason = "cancelled"
                    break
                if not tool_calls:
                    break

                calls = [tool_calls[k] for k in sorted(tool_calls)]
                messages.append({
                    "role": "assistant",
                    "content": "".join(turn_text) or None,
                    "tool_calls": [
                        {
                            "id": c["id"] or f"call_{i}",
                            "type": "function",
                            "function": {"name": c["name"], "arguments": c["arguments"] or "{}"},
                        }
                        for i, c in enumerate(calls)
                    ],
                })
                for i, call in enumerate(calls):
                    call_id = call["id"] or f"call_{i}"
                    try:
                        args = json.loads(call["arguments"] or "{}")
                        if not isinstance(args, dict):
                            args = {}
                    except json.JSONDecodeError:
                        args = {}
                    yield {"event": "tool", "data": json.dumps({
                        "id": call_id, "name": call["name"], "arguments": args,
                    })}
                    result_text, info = await _execute_tool(call["name"], args, user, conv["_id"])
                    entry = {
                        "name": call["name"],
                        "arguments": args,
                        "ok": bool(info.get("ok", True)),
                        "summary": info.get("summary") or result_text[:200],
                    }
                    tools_used.append(entry)
                    yield {"event": "tool_result", "data": json.dumps({
                        "id": call_id, "name": entry["name"], "ok": entry["ok"], "summary": entry["summary"],
                    })}
                    messages.append({"role": "tool", "tool_call_id": call_id, "content": result_text[:8000]})
        except Exception as e:
            log.exception("agent stream error: %s", e)
            buffer.append(f"\n\n[Agent error: {type(e).__name__}: {e}]")
            finish_reason = "error"
            yield {"event": "error", "data": json.dumps({"message": str(e)})}
        finally:
            full = "".join(buffer).strip()
            now2 = datetime.now(tz=UTC)
            assistant_doc = {
                "conversationId": conv["_id"],
                "userId": user["_id"],
                "role": "assistant",
                "content": full,
                "tokens": _count_tokens(full),
                "model": model_name,
                "metadata": {
                    "provider": "internal",
                    "model": model,
                    "finish_reason": finish_reason,
                    "iterations": iterations,
                    "latency_ms": int((time.perf_counter() - start) * 1000),
                    "ttft_ms": int(((first_token_at or time.perf_counter()) - start) * 1000),
                    "tools": tools_used,
                },
                "parentId": None,
                "createdAt": now2,
            }
            res = await mongo.messages().insert_one(assistant_doc)
            await mongo.conversations().update_one(
                {"_id": conv["_id"]},
                {"$set": {"updatedAt": now2, "lastMessageAt": now2}},
            )
            yield {"event": "done", "data": json.dumps({
                "assistantMessageId": str(res.inserted_id),
                "tokens": assistant_doc["tokens"],
                "iterations": iterations,
                "tools": len(tools_used),
            })}

    return EventSourceResponse(event_gen())



