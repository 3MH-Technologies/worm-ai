"""Streaming client for our chat backend (notrack.ai).

Every chat reply goes through POST /api/dispatch and comes back as an SSE
stream — that's what keeps the UI feeling instant.

Auth is cookie-based: drop your browser cookie string into NOTRACK_COOKIE
(format: "k1=v1; k2=v2") and the client will attach it to every request.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# Model codes accepted by /api/dispatch ("model" field).
# Display names are the site's own internal model names (no vendor branding).
NOTRACK_MODELS: dict[str, str] = {
    "C": "Worm Core",
    "B": "Worm Pro",
    "A": "Worm Flash",
    "F": "Worm Synth",
}

NOTRACK_MODEL_DESCRIPTIONS: dict[str, str] = {
    "C": "Balanced internal model (default)",
    "B": "General-purpose internal model",
    "A": "Fast internal model",
    "F": "Multi-model internal synthesis",
}

NOTRACK_PERSONAS: tuple[str, ...] = (
    "normal", "creative", "precise", "concise", "socratic", "tutor", "coder",
)

_MAX_ATTEMPTS = 5


class NotrackError(RuntimeError):
    """Raised when the notrack.ai API fails permanently."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class NotrackClient:
    """Process-wide async client. Lazily built so settings are read at first use."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()

    async def _get(self) -> httpx.AsyncClient:
        async with self._lock:
            if self._client is None:
                settings = get_settings()
                client = httpx.AsyncClient(
                    base_url=settings.notrack_base.rstrip("/"),
                    timeout=httpx.Timeout(120.0, connect=30.0),
                    headers={"User-Agent": _UA, "Accept-Encoding": "identity"},
                    follow_redirects=True,
                )
                for pair in (settings.notrack_cookie or "").split(";"):
                    pair = pair.strip()
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        client.cookies.set(k.strip(), v.strip())
                self._client = client
            return self._client

    async def close(self) -> None:
        async with self._lock:
            if self._client is not None:
                await self._client.aclose()
                self._client = None

    async def stream_dispatch(
        self,
        user_input: str,
        *,
        chat_id: str | None = None,
        model: str = "C",
        persona: str = "normal",
        max_turns: int = 6,
        attachments: list[str] | None = None,
        regenerate: bool = False,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield parsed SSE events from /api/dispatch.

        Event shapes:
          {"type": "chat_meta", "chat_id": str}
          {"type": "thinking", "speaker": "A"|"B"|"C"|"F"}
          {"type": "delta", "text": str}
          {"type": "turn_end"}
          {"type": "error", "code": str|None, "message": str}
          {"type": "notice", "kind": "ctx_cut"|"busy", "message": str}
        """
        if model not in NOTRACK_MODELS:
            model = "C"
        if persona not in NOTRACK_PERSONAS:
            persona = "normal"
        body: dict[str, Any] = {
            "user_input": user_input,
            "mode": "usual",
            "model": model,
            "persona": persona,
            "max_turns": max_turns,
            "chat_id": chat_id,
            "attachments": attachments or [],
            "regenerate": regenerate,
            "edit": False,
            "edit_mid": None,
            "via": "typed",
        }

        attempt = 0
        while True:
            attempt += 1
            retry = False
            client = await self._get()
            try:
                async with client.stream("POST", "/api/dispatch", json=body) as resp:
                    if resp.status_code == 429:
                        if attempt >= _MAX_ATTEMPTS:
                            raise NotrackError(
                                "rate limit exceeded; try again in a minute", code="ratelimit"
                            )
                        wait = attempt * 4
                        log.warning("notrack 429; retrying in %ss (attempt %s)", wait, attempt)
                        await asyncio.sleep(wait)
                        continue
                    if resp.status_code != 200:
                        raw_body = (await resp.aread()).decode("utf-8", "replace")
                        try:
                            data = json.loads(raw_body)
                            msg = data.get("error") or data.get("message") or raw_body
                        except Exception:
                            msg = raw_body
                        raise NotrackError(f"HTTP {resp.status_code}: {msg}")

                    turn_had_delta = False
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw:
                            continue
                        try:
                            ev = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        et = ev.get("type")
                        if et == "chat_meta":
                            yield {"type": "chat_meta", "chat_id": ev.get("chat_id")}
                        elif et == "thinking":
                            turn_had_delta = False
                            yield {"type": "thinking", "speaker": ev.get("speaker")}
                        elif et == "delta":
                            chunk = ev.get("chunk", "")
                            if chunk:
                                turn_had_delta = True
                                yield {"type": "delta", "text": chunk}
                        elif et in ("message", "consensus"):
                            content = ev.get("content", "")
                            if content and not turn_had_delta:
                                yield {"type": "delta", "text": content}
                            turn_had_delta = False
                            yield {"type": "turn_end"}
                        elif et == "error":
                            if ev.get("code") == "ratelimit":
                                if attempt >= _MAX_ATTEMPTS:
                                    raise NotrackError(
                                        ev.get("content") or "rate limited", code="ratelimit"
                                    )
                                wait = attempt * 4
                                log.warning("notrack ratelimit event; retry in %ss", wait)
                                await asyncio.sleep(wait)
                                retry = True
                                break
                            yield {
                                "type": "error",
                                "code": ev.get("code"),
                                "message": ev.get("content", ""),
                            }
                        elif et == "ctx_cut":
                            yield {"type": "notice", "kind": "ctx_cut", "message": ""}
                        elif et == "busy":
                            yield {"type": "notice", "kind": "busy", "message": ev.get("why", "")}
            except (httpx.TransportError, httpx.TimeoutException) as e:
                if attempt >= 3:
                    raise NotrackError(f"connection error: {e}") from e
                log.warning("notrack transport error (%s); retrying", e)
                await asyncio.sleep(attempt * 2)
                continue
            if not retry:
                return

    async def complete(self, user_input: str, **kwargs: Any) -> tuple[str, str | None]:
        """Non-streaming helper: collect the full reply. Returns (text, chat_id)."""
        parts: list[str] = []
        chat_id: str | None = None
        async for ev in self.stream_dispatch(user_input, **kwargs):
            if ev["type"] == "delta":
                parts.append(ev["text"])
            elif ev["type"] == "turn_end":
                parts.append("\n\n")
            elif ev["type"] == "chat_meta":
                chat_id = ev.get("chat_id") or chat_id
            elif ev["type"] == "error":
                raise NotrackError(ev.get("message") or "unknown error", code=ev.get("code"))
        return "".join(parts).strip(), chat_id


_client = NotrackClient()


def get_notrack() -> NotrackClient:
    """Process-wide shared client (keeps the cookie jar between requests)."""
    return _client


def count_tokens(text: str) -> int:
    """Cheap token estimate (~4 chars per token)."""
    return max(1, len(text) // 4)


__all__ = [
    "NOTRACK_MODELS",
    "NOTRACK_MODEL_DESCRIPTIONS",
    "NOTRACK_PERSONAS",
    "NotrackClient",
    "NotrackError",
    "count_tokens",
    "get_notrack",
]
