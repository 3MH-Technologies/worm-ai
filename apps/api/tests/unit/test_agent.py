"""Unit tests for Worm Agent helpers (no DB / no network)."""

from __future__ import annotations

from app.api.v1.agent import AGENT_SYSTEM_PROMPT, TOOLS, _file_type


def test_file_type_mapping():
    assert _file_type("src/main.py", None) == "code"
    assert _file_type("app.tsx", None) == "code"
    assert _file_type("README.md", None) == "markdown"
    assert _file_type("notes.txt", None) == "document"
    assert _file_type("data.bin", None) == "document"
    assert _file_type("anything", "python") == "code"
    assert _file_type("anything", "markdown") == "markdown"


def test_tools_schema_is_valid_openai_format():
    names = {t["function"]["name"] for t in TOOLS}
    assert names == {"create_file", "read_file", "list_files", "delete_file", "web_search", "fetch_url"}
    for t in TOOLS:
        assert t["type"] == "function"
        assert t["function"]["description"]
        params = t["function"]["parameters"]
        assert params["type"] == "object"
        if t["function"]["name"] in ("create_file", "read_file", "delete_file", "web_search", "fetch_url"):
            assert params.get("required")


def test_system_prompt_branding():
    assert "Worm Agent" in AGENT_SYSTEM_PROMPT
    assert "3MH" in AGENT_SYSTEM_PROMPT
    assert "create_file" in AGENT_SYSTEM_PROMPT
    # Vendor names must not leak into the agent's identity.
    assert "DeepSeek" not in AGENT_SYSTEM_PROMPT
    assert "NoTrack" not in AGENT_SYSTEM_PROMPT
