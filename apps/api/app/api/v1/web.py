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

from app.api.deps import current_user
from app.core.config import get_settings
from app.models.extras import WebSearchRequest, WebSearchResponse, WebSearchResult

log = logging.getLogger(__name__)
router = APIRouter(prefix="/web", tags=["web"])


_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def _clean_url(href: str) -> str:
    """Undo search-engine redirect wrappers so results carry the real target URL."""
    if not href:
        return ""
    # DDG: //duckduckgo.com/l/?uddg=<encoded>
    if "uddg=" in href:
        parsed = urlparse("https:" + href if href.startswith("//") else href)
        qs = parse_qs(parsed.query)
        return unquote(qs.get("uddg", [href])[0])
    # Bing: /ck/a?...&u=a1<base64url(real url)>
    if "/ck/a?" in href:
        parsed = urlparse(href if href.startswith("http") else "https://www.bing.com" + href)
        raw = parse_qs(parsed.query).get("u", [""])[0]
        if raw.startswith("a1"):
            b64 = raw[2:] + "=" * (-len(raw[2:]) % 4)
            try:
                import base64
                return base64.urlsafe_b64decode(b64).decode("utf-8", "replace")
            except Exception:
                return ""
    return href


def _results_from(soup, item_sel: str, link_sel: str, snippet_sel: str, max_results: int) -> list[WebSearchResult]:
    out: list[WebSearchResult] = []
    for item in soup.select(item_sel)[:max_results]:
        a = item.select_one(link_sel)
        if not a:
            continue
        href = _clean_url(a.get("href", ""))
        if not href.startswith("http"):
            continue
        snippet_el = item.select_one(snippet_sel)
        out.append(WebSearchResult(
            title=a.get_text(strip=True),
            url=href,
            snippet=snippet_el.get_text(" ", strip=True) if snippet_el else "",
            score=1.0 - (len(out) * 0.05),
        ))
    return out


async def _ddg_instant_answer(client: httpx.AsyncClient, query: str, max_results: int) -> list[WebSearchResult]:
    """Keyless DDG instant-answer JSON — a small but reliably relevant fallback."""
    try:
        resp = await client.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
        )
        data = resp.json()
    except Exception as e:
        log.warning("search backend failed url=ddg-ia err=%s", e)
        return []
    out: list[WebSearchResult] = []
    abstract = data.get("AbstractText") or ""
    if abstract and data.get("AbstractURL"):
        out.append(WebSearchResult(
            title=data.get("Heading") or data.get("AbstractSource") or query,
            url=data["AbstractURL"],
            snippet=abstract,
            score=1.0,
        ))
    for bucket in (data.get("Results") or []) + (data.get("RelatedTopics") or []):
        if len(out) >= max_results:
            break
        if isinstance(bucket, dict) and bucket.get("FirstURL"):
            out.append(WebSearchResult(
                title=(bucket.get("Text") or "").split(" - ")[0][:120] or query,
                url=bucket["FirstURL"],
                snippet=bucket.get("Text") or "",
                score=1.0 - 0.05 * len(out),
            ))
        elif isinstance(bucket, dict):
            for sub in bucket.get("Topics") or []:
                if len(out) >= max_results:
                    break
                if isinstance(sub, dict) and sub.get("FirstURL"):
                    out.append(WebSearchResult(
                        title=(sub.get("Text") or "").split(" - ")[0][:120] or query,
                        url=sub["FirstURL"],
                        snippet=sub.get("Text") or "",
                        score=1.0 - 0.05 * len(out),
                    ))
    return out[:max_results]


async def _ddg_search(query: str, max_results: int) -> list[WebSearchResult]:
    """Keyless web search with fallbacks.

    DuckDuckGo intermittently answers with a bot-challenge page (HTTP 202, no
    result markup), which used to surface as an empty search and a failed
    research run — so retry, then fall back to DDG's instant-answer JSON and
    finally to Bing's HTML. The first backend that yields hits wins.
    """
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=_BROWSER_HEADERS) as client:
        for attempt in range(2):
            for url in ("https://html.duckduckgo.com/html/", "https://lite.duckduckgo.com/lite/"):
                try:
                    resp = await client.get(url, params={"q": query})
                    resp.raise_for_status()
                except Exception as e:
                    log.warning("search backend failed url=%s err=%s", url, e)
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")
                hits = _results_from(soup, ".result", "a.result__a", ".result__snippet", max_results)
                if not hits:
                    hits = _results_from(soup, "tr", "a", "td", max_results)
                hits = [h for h in hits if "duckduckgo.com" not in h.url]
                if hits:
                    return hits[:max_results]
            await asyncio.sleep(1.5 * (attempt + 1))

        hits = await _ddg_instant_answer(client, query, max_results)
        if hits:
            return hits

        # Last resort: Bing's result markup is stable and needs no key.
        try:
            resp = await client.get("https://www.bing.com/search", params={"q": query, "count": max_results})
            resp.raise_for_status()
        except Exception as e:
            log.warning("search backend failed url=bing err=%s", e)
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        hits = _results_from(soup, "li.b_algo", "h2 a", ".b_caption p", max_results)
        if not hits:
            hits = _results_from(soup, "li.b_algo", "h2 a", ".b_caption", max_results)
        return hits[:max_results]


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
            "User-Agent": "Mozilla/5.0 (compatible; worm-ai/0.1)"
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
    text = await _fetch_content(url)
    return {"url": url, "content": text, "fetchedAt": datetime.now(tz=UTC)}
