"""Unit tests for the 3MH DeepSeek proxy client (offline, via MockTransport)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.services import deepseek


def _openai_sse(chunks: list[dict]) -> bytes:
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks)
    return (body + "data: [DONE]\n\n").encode()


def _chunk(delta: dict) -> dict:
    return {"choices": [{"index": 0, "delta": delta}]}


def _patch_transport(monkeypatch, chunks: list[dict] | None = None, status: int = 200, body: bytes | None = None):
    async def handler(request: httpx.Request) -> httpx.Response:
        content = body if body is not None else _openai_sse(chunks or [])
        return httpx.Response(status, headers={"content-type": "text/event-stream"}, content=content)

    transport = httpx.MockTransport(handler)

    async def fake_get(self):  # noqa: ANN001
        return httpx.AsyncClient(base_url="https://proxy.test", transport=transport)

    monkeypatch.setattr(deepseek.DeepSeekClient, "_get", fake_get)


async def test_stream_chat_parses_text_and_reasoning(monkeypatch):
    _patch_transport(monkeypatch, [
        _chunk({"reasoning_content": "Let me think…"}),
        _chunk({"content": "Hello"}),
        _chunk({"content": " world"}),
        _chunk({}),
    ])
    client = deepseek.DeepSeekClient()
    events = [ev async for ev in client.stream_chat([{"role": "user", "content": "hi"}])]

    assert [e["type"] for e in events] == ["reasoning", "text", "text"]
    assert events[0]["text"] == "Let me think…"
    assert events[1]["text"] + events[2]["text"] == "Hello world"


async def test_stream_chat_parses_tool_calls(monkeypatch):
    _patch_transport(monkeypatch, [
        _chunk({"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "create_file", "arguments": '{"path":'}}]}),
        _chunk({"tool_calls": [{"index": 0, "function": {"arguments": ' "a.py", "content": "print(1)"}'}}]}),
    ])
    client = deepseek.DeepSeekClient()
    events = [ev async for ev in client.stream_chat([{"role": "user", "content": "hi"}])]

    assert all(e["type"] == "tool_call_delta" for e in events)
    assert events[0]["id"] == "call_1"
    assert events[0]["name"] == "create_file"
    combined = events[0]["arguments"] + events[1]["arguments"]
    args = json.loads(combined)
    assert args["path"] == "a.py"


async def test_unauthorized_raises(monkeypatch):
    _patch_transport(monkeypatch, status=401, body=b'{"error":{"message":"bad token"}}')
    client = deepseek.DeepSeekClient()
    with pytest.raises(deepseek.DeepSeekError) as ei:
        async for _ in client.stream_chat([{"role": "user", "content": "hi"}]):
            pass
    assert ei.value.code == "unauthorized"


def test_agent_models_catalogue():
    assert set(deepseek.AGENT_MODELS) == {"deepseek-chat", "deepseek-reasoner"}
    for m in deepseek.AGENT_MODELS.values():
        assert m["name"] and m["description"]
