"""Client for the Worm Agent's model API — the 3MH Technologies proxy.

Credits: https://3mh.pages.dev/ · https://t.me/j49_c

We speak to the OpenAI-compatible /v1/chat/completions endpoint, which gives
us tools (function calling) and streaming for free. Proof-of-work is handled
server-side by the proxy, so this client never solves anything itself.
A DEEPSEEK token is required — see settings.deepseek_token.
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

_UA = "worm-ai-agent/1.0 (+https://3mh.pages.dev)"

# Agent models exposed to the UI (internal names — no vendor branding).
AGENT_MODELS: dict[str, dict[str, str]] = {
    "deepseek-chat": {
        "name": "Worm Agent",
        "description": "Fast internal model — file tools, web search, research",
    },
    "deepseek-reasoner": {
        "name": "Worm Agent R1",
        "description": "Reasoning internal model for complex tasks",
    },
}

_MAX_ATTEMPTS = 4


class DeepSeekError(RuntimeError):
    """Raised when the DeepSeek proxy fails permanently."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class DeepSeekClient:
    """Async client for the 3MH DeepSeek proxy (OpenAI-compatible subset)."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()

    async def _get(self) -> httpx.AsyncClient:
        async with self._lock:
            if self._client is None:
                settings = get_settings()
                headers: dict[str, str] = {
                    "User-Agent": _UA,
                    "Accept-Encoding": "identity",
                }
                if settings.deepseek_token:
                    headers["Authorization"] = f"Bearer {settings.deepseek_token}"
                    headers["x-deepseek-token"] = settings.deepseek_token
                self._client = httpx.AsyncClient(
                    base_url=settings.deepseek_proxy_base.rstrip("/"),
                    timeout=httpx.Timeout(300.0, connect=30.0),
                    headers=headers,
                    follow_redirects=True,
                )
            return self._client

    async def close(self) -> None:
        async with self._lock:
            if self._client is not None:
                await self._client.aclose()
                self._client = None

    @staticmethod
    def configured() -> bool:
        return bool(get_settings().deepseek_token)

    def _auth_body(self) -> dict[str, Any]:
        token = get_settings().deepseek_token
        return {"token": token} if token else {}

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 8192,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream an OpenAI-format completion from the proxy.

        Yields normalized events:
          {"type": "text", "text": str}
          {"type": "reasoning", "text": str}
          {"type": "tool_call_delta", "index": int, "id": str|None,
           "name": str|None, "arguments": str}
        """
        settings = get_settings()
        body: dict[str, Any] = {
            "model": model or settings.deepseek_model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **self._auth_body(),
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        attempt = 0
        while True:
            attempt += 1
            client = await self._get()
            try:
                async with client.stream("POST", "/v1/chat/completions", json=body) as resp:
                    if resp.status_code == 429 and attempt < _MAX_ATTEMPTS:
                        wait = attempt * 3
                        log.warning("deepseek 429; retrying in %ss (attempt %s)", wait, attempt)
                        await asyncio.sleep(wait)
                        continue
                    if resp.status_code == 401:
                        raise DeepSeekError(
                            "Model token rejected (401). Set DEEPSEEK_TOKEN on the server.",
                            code="unauthorized",
                        )
                    if resp.status_code != 200:
                        raw = (await resp.aread()).decode("utf-8", "replace")
                        try:
                            data = json.loads(raw)
                            err = data.get("error")
                            msg = err.get("message") if isinstance(err, dict) else err
                            msg = msg or data.get("message") or raw
                        except Exception:
                            msg = raw
                        raise DeepSeekError(f"HTTP {resp.status_code}: {msg}")

                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw or raw == "[DONE]":
                            continue
                        try:
                            chunk = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        reasoning = delta.get("reasoning_content")
                        if reasoning:
                            yield {"type": "reasoning", "text": reasoning}
                        content = delta.get("content")
                        if content:
                            yield {"type": "text", "text": content}
                        for tc in delta.get("tool_calls") or []:
                            fn = tc.get("function") or {}
                            yield {
                                "type": "tool_call_delta",
                                "index": int(tc.get("index") or 0),
                                "id": tc.get("id"),
                                "name": fn.get("name"),
                                "arguments": fn.get("arguments") or "",
                            }
            except (httpx.TransportError, httpx.TimeoutException) as e:
                if attempt >= _MAX_ATTEMPTS:
                    raise DeepSeekError(f"connection error: {e}") from e
                log.warning("deepseek transport error (%s); retrying", e)
                await asyncio.sleep(attempt * 2)
                continue
            return


_client = DeepSeekClient()


def get_deepseek() -> DeepSeekClient:
    """Process-wide shared client."""
    return _client


__all__ = [
    "AGENT_MODELS",
    "DeepSeekClient",
    "DeepSeekError",
    "get_deepseek",
]

