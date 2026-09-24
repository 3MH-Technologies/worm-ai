"""Web search integration. Default: DuckDuckGo HTML scraper (no key).
Alternative: Serper, Tavily when keys are set."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import UTC, datetime
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import current_user, enforce_approval
from app.core.config import get_settings
from app.models.extras import WebSearchRequest, WebSearchResponse, WebSearchResult

log = logging.getLogger(__name__)
router = APIRouter(prefix="/web", tags=["web"])


async def _ddg_search(query: str, max_results: int) -> list[WebSearchResult]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=headers) as client:
        resp = await client.get("https://duckduckgo.com/html/", params={"q": query})
        resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    out: list[WebSearchResult] = []
    for item in soup.select(".result")[:max_results]:
        a = item.select_one("a.result__a")
        if not a:
            continue
        title = a.get_text(strip=True)
        href = a.get("href", "")
        # DDG wraps URLs in a redirect: //duckduckgo.com/l/?uddg=<encoded>
        if "uddg=" in href:
            parsed = urlparse("https:" + href if href.startswith("//") else href)
            qs = parse_qs(parsed.query)
            href = unquote(qs.get("uddg", [href])[0])
        snippet_el = item.select_one(".result__snippet")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        out.append(WebSearchResult(
            title=title, url=href, snippet=snippet, score=1.0 - (len(out) * 0.05),
        ))
    return out


async def _serper_search(query: str, max_results: int, api_key: str) -> list[WebSearchResult]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://google.serper.dev/search",
            json={"q": query, "num": max_results},
            headers={"X-API-KEY": api_key},
        )
        resp.raise_for_status()
    data = resp.json()
    out: list[WebSearchResult] = []
    for item in data.get("organic", [])[:max_results]:
        out.append(WebSearchResult(
            title=item.get("title", ""),
            url=item.get("link", ""),
            snippet=item.get("snippet", ""),
            score=1.0 - (len(out) * 0.05),
        ))
    return out


async def _tavily_search(query: str, max_results: int, api_key: str) -> list[WebSearchResult]:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query, "max_results": max_results},
        )
        resp.raise_for_status()
    data = resp.json()
    return [
        WebSearchResult(
            title=r.get("title", ""),
            url=r.get("url", ""),
            snippet=r.get("content", ""),
            score=float(r.get("score", 0.5)),
        )
        for r in data.get("results", [])[:max_results]
    ]


async def _fetch_content(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (compatible; WormGPT/0.1)"
        }) as client:
            r = await client.get(url)
            r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        return text[:8000]
    except Exception as e:
        log.warning("fetch failed url=%s err=%s", url, e)
        return ""


@router.post("/search", response_model=WebSearchResponse)
async def search(payload: WebSearchRequest, user=Depends(current_user)) -> WebSearchResponse:
    await enforce_approval(user)
    settings = get_settings()
    start = time.perf_counter()
    provider = settings.web_search_provider
    results: list[WebSearchResult] = []
    try:
        if provider == "serper" and settings.serper_api_key:
            results = await _serper_search(payload.query, payload.maxResults, settings.serper_api_key)
        elif provider == "tavily" and settings.tavily_api_key:
            results = await _tavily_search(payload.query, payload.maxResults, settings.tavily_api_key)
        else:
            provider = "duckduckgo"
            results = await _ddg_search(payload.query, payload.maxResults)
    except Exception as e:
        log.exception("web search failed")
        raise HTTPException(502, f"search provider error: {e}") from None

    if payload.fetchContent:
        contents = await asyncio.gather(*[_fetch_content(r.url) for r in results], return_exceptions=True)
        for r, c in zip(results, contents, strict=False):
            if isinstance(c, str):
                r.content = c
    return WebSearchResponse(
        query=payload.query,
        results=results,
        provider=provider,
        took_ms=int((time.perf_counter() - start) * 1000),
    )


@router.get("/fetch")
async def fetch_url(url: str, user=Depends(current_user)) -> dict:
    """Fetch a URL and return sanitised text content."""
    await enforce_approval(user)
    text = await _fetch_content(url)
    return {"url": url, "content": text, "fetchedAt": datetime.now(tz=UTC)}
