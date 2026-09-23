"""Unit tests for the notrack.ai client (offline, via httpx MockTransport)."""

from __future__ import annotations

import httpx
import pytest

from app.services import notrack


def _sse_bytes(events: list[dict]) -> bytes:
    import json
    return b"".join(f"data: {json.dumps(e)}\n\n".encode() for e in events)


def _patch_transport(monkeypatch, events: list[dict], status: int = 200):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            headers={"content-type": "text/event-stream"},
            content=_sse_bytes(events),
        )

    transport = httpx.MockTransport(handler)

    async def fake_get(self):  # noqa: ANN001
        client = httpx.AsyncClient(base_url="https://notrack.ai", transport=transport)
        return client

    monkeypatch.setattr(notrack.NotrackClient, "_get", fake_get)


async def test_stream_dispatch_parses_events(monkeypatch):
    _patch_transport(monkeypatch, [
        {"type": "chat_meta", "chat_id": "chat-1"},
        {"type": "thinking", "speaker": "C"},
        {"type": "delta", "chunk": "Hel"},
        {"type": "delta", "chunk": "lo"},
        {"type": "message", "content": "Hello"},
    ])
    client = notrack.NotrackClient()
    events = [ev async for ev in client.stream_dispatch("hi")]

    assert [e["type"] for e in events] == ["chat_meta", "thinking", "delta", "delta", "turn_end"]
    assert events[0]["chat_id"] == "chat-1"
    assert "".join(e["text"] for e in events if e["type"] == "delta") == "Hello"


async def test_complete_returns_text_and_chat_id(monkeypatch):
    _patch_transport(monkeypatch, [
        {"type": "chat_meta", "chat_id": "chat-2"},
        {"type": "delta", "chunk": "Hel"},
        {"type": "delta", "chunk": "lo"},
        {"type": "message", "content": "Hello"},
    ])
    client = notrack.NotrackClient()
    text, chat_id = await client.complete("hi")
    assert text == "Hello"
    assert chat_id == "chat-2"


async def test_message_content_used_when_no_deltas(monkeypatch):
    _patch_transport(monkeypatch, [
        {"type": "thinking", "speaker": "A"},
        {"type": "message", "content": "Full answer"},
    ])
    client = notrack.NotrackClient()
    text, _ = await client.complete("hi")
    assert text == "Full answer"


async def test_error_event_raises(monkeypatch):
    _patch_transport(monkeypatch, [
        {"type": "error", "code": "denied", "content": "no access"},
    ])
    client = notrack.NotrackClient()
    with pytest.raises(notrack.NotrackError):
        await client.complete("hi")


def test_models_catalogue_is_static_and_keyless():
    from app.api.v1.models import _to_out
    outs = [_to_out(code) for code in notrack.NOTRACK_MODELS]
    assert {o.id for o in outs} == {"A", "B", "C", "F"}
    assert all(o.provider == "internal" for o in outs)
    assert all(not o.hasApiKey for o in outs)
    assert all(o.enabled for o in outs)
