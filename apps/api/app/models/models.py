"""Model management and system prompt schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# Engines are internal; legacy values kept so old DB documents still parse.
Provider = Literal[
    "internal", "notrack", "deepseek", "groq", "openai", "anthropic", "gemini", "qwen", "ollama", "custom"
]


class ModelOut(BaseModel):
    """Public-facing model representation."""
    id: str
    name: str
    provider: Provider
    endpoint: str | None = None
    temperature: float
    maxTokens: int
    topP: float
    systemPromptId: str | None = None
    systemPromptName: str | None = None
    enabled: bool
    description: str | None = None
    displayName: str | None = None
    avatar: str | None = None
    tags: list[str]
    createdAt: datetime
    updatedAt: datetime
    hasApiKey: bool = False


class SystemPromptCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1, max_length=200_000)
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    active: bool = True


class SystemPromptUpdate(BaseModel):
    name: str | None = None
    content: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    active: bool | None = None
    changelog: str | None = None


class SystemPromptVersion(BaseModel):
    version: int
    content: str
    changelog: str | None = None
    createdAt: datetime


class SystemPromptOut(BaseModel):
    id: str
    name: str
    description: str | None = None
    tags: list[str]
    active: bool
    currentVersion: int
    versions: list[SystemPromptVersion] = Field(default_factory=list)
    createdAt: datetime
    updatedAt: datetime


class SystemPromptSummary(BaseModel):
    """Minimal info for non-admin users (content is NEVER sent)."""
    id: str
    name: str
    description: str | None = None
