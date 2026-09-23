"""Research mode: multi-source research, citations, long-form reports.
LLM synthesis runs through notrack.ai."""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sse_starlette.sse import EventSourceResponse

from app.api.deps import current_user, enforce_approval, rate_limit
from app.api.v1.web import _ddg_search, _fetch_content, _serper_search, _tavily_search
from app.core.config import get_settings
from app.db import mongo
from app.models.extras import ResearchRequest, ResearchReport, ResearchSource
from app.services import notrack

log = logging.getLogger(__name__)
router = APIRouter(prefix="/research", tags=["research"])


def _model_code(model_id: str | None) -> str:
    code = (model_id or get_settings().notrack_model or "C").strip().upper()
    return code if code in notrack.NOTRACK_MODELS else "C"


async def _gather_sources(query: str, max_sources: int) -> list[ResearchSource]:
    s = get_settings()
    results: list[ResearchSource] = []
    try:
        if s.web_search_provider == "serper" and s.serper_api_key:
            results = [ResearchSource(**r.model_dump()) for r in await _serper_search(query, max_sources, s.serper_api_key)]
        elif s.web_search_provider == "tavily" and s.tavily_api_key:
            results = [ResearchSource(**r.model_dump()) for r in await _tavily_search(query, max_sources, s.tavily_api_key)]
        else:
            results = [ResearchSource(**r.model_dump()) for r in await _ddg_search(query, max_sources)]
    except Exception as e:
        log.warning("research.search.failed err=%s", e)
        results = []
    # fetch content for top sources
    if results:
        contents = await __import__("asyncio").gather(*[_fetch_content(r.url) for r in results], return_exceptions=True)
        for r, c in zip(results, contents, strict=False):
            if isinstance(c, str) and c:
                r.content = c
    return results


def _build_prompt(query: str, sources: list[ResearchSource]) -> str:
    s_blocks = []
    for i, src in enumerate(sources, start=1):
        body = (src.content or src.snippet)[:3500]
        s_blocks.append(f"[{i}] {src.title}\nURL: {src.url}\n{body}\n")
    sources_blob = "\n\n".join(s_blocks)
    system = (
        "You are a meticulous research analyst. Synthesise the provided sources into a "
        "long-form, well-cited report. Use inline numeric citations like [1], [2] that "
        "correspond to the sources. Avoid speculation. Quote or paraphrase faithfully. "
        "Structure: Executive Summary, Key Findings, Detailed Analysis, Caveats, References."
    )
    user_prompt = (
        f"Question: {query}\n\nSOURCES:\n{sources_blob}\n\n"
        "Produce a thorough report with inline numeric citations. End with a 'References' "
        "list that reproduces each source title + URL."
    )
    return f"{system}\n\n{user_prompt}"


@router.post("/run", response_model=ResearchReport)
async def run_research(
    payload: ResearchRequest,
    background: BackgroundTasks,
    user=Depends(current_user),
    _: None = Depends(rate_limit),
) -> ResearchReport:
    await enforce_approval(user)
    sources = await _gather_sources(payload.query, payload.maxSources)
    if not sources:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "no sources retrieved")

    prompt = _build_prompt(payload.query, sources)
    report_text, _ = await notrack.get_notrack().complete(prompt, model=_model_code(payload.modelId))

    citations = sorted({int(m.group(1)) for m in re.finditer(r"\[(\d+)\]", report_text) if 1 <= int(m.group(1)) <= len(sources)})
    summary = report_text.split("\n\n", 1)[0][:500]

    canvas_id = None
    if payload.saveAsCanvas:
        canvas = await mongo.canvases().insert_one({
            "ownerId": user["_id"],
            "title": f"Research: {payload.query[:80]}",
            "type": "research",
            "content": report_text,
            "metadata": {"sources": [s.model_dump() for s in sources]},
            "currentVersion": 1,
            "createdAt": datetime.now(tz=timezone.utc),
            "updatedAt": datetime.now(tz=timezone.utc),
        })
        canvas_id = str(canvas.inserted_id)
        await mongo.canvas_versions().insert_one({
            "canvasId": canvas.inserted_id,
            "version": 1,
            "content": report_text,
            "commitMessage": "research",
            "authorId": user["_id"],
            "createdAt": datetime.now(tz=timezone.utc),
        })

    report = ResearchReport(
        id=str(ObjectId()),
        query=payload.query,
        summary=summary,
        report=report_text,
        sources=sources,
        citations=citations,
        modelId=_model_code(payload.modelId),
        canvasId=canvas_id,
        createdAt=datetime.now(tz=timezone.utc),
    )
    return report


@router.post("/stream")
async def stream_research(
    payload: ResearchRequest,
    user=Depends(current_user),
    _: None = Depends(rate_limit),
):
    """SSE variant: emits sources first, then streams the report deltas, then a done event."""
    await enforce_approval(user)
    sources = await _gather_sources(payload.query, payload.maxSources)
    prompt = _build_prompt(payload.query, sources)
    model = _model_code(payload.modelId)

    async def gen():
        yield {"event": "sources", "data": json.dumps({
            "sources": [s.model_dump(mode="json") for s in sources],
        })}
        buffer: list[str] = []
        try:
            async for ev in notrack.get_notrack().stream_dispatch(prompt, model=model):
                if ev["type"] == "delta":
                    buffer.append(ev["text"])
                    yield {"event": "delta", "data": json.dumps({"text": ev["text"]})}
                elif ev["type"] == "error":
                    yield {"event": "error", "data": json.dumps({"message": ev.get("message") or "upstream error"})}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"message": str(e)})}
        yield {"event": "done", "data": json.dumps({
            "report": "".join(buffer),
            "tokens": notrack.count_tokens("".join(buffer)),
        })}
    return EventSourceResponse(gen())
