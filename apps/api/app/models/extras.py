"""Canvas, research, search, memory, web search schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

CanvasType = Literal["document", "code", "markdown", "project", "research"]


class CanvasCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    type: CanvasType = "document"
    content: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    conversationId: str | None = None


class CanvasUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    metadata: dict[str, Any] | None = None
    commitMessage: str | None = None


class CanvasVersion(BaseModel):
    version: int
    content: str
    commitMessage: str | None = None
    authorId: str
    createdAt: datetime


class CanvasOut(BaseModel):
    id: str
    ownerId: str
    title: str
    type: CanvasType
    content: str
    metadata: dict[str, Any]
    conversationId: str | None = None
    currentVersion: int
    createdAt: datetime
    updatedAt: datetime


class ResearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=1000)
    maxSources: int = Field(default=8, ge=1, le=20)
    modelId: str | None = None
    saveAsCanvas: bool = False


class ResearchSource(BaseModel):
    title: str
    url: str
    snippet: str
    content: str | None = None
    score: float = 0.0
    favicon: str | None = None
    publishedAt: datetime | None = None


class ResearchReport(BaseModel):
    id: str
    query: str
    summary: str
    report: str
    sources: list[ResearchSource]
    citations: list[int]
    modelId: str | None = None
    canvasId: str | None = None
    createdAt: datetime


class WebSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    maxResults: int = Field(default=8, ge=1, le=20)
    fetchContent: bool = False


class WebSearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    content: str | None = None
    score: float = 0.0
    favicon: str | None = None
    publishedAt: datetime | None = None


class WebSearchResponse(BaseModel):
    query: str
    results: list[WebSearchResult]
    provider: str
    took_ms: int


class MemoryItem(BaseModel):
    id: str
    userId: str
    kind: Literal["long_term", "context", "session", "preference"]
    content: str
    weight: float = 1.0
    source: str | None = None
    createdAt: datetime
    lastUsedAt: datetime | None = None


class MemoryCreate(BaseModel):
    kind: Literal["long_term", "context", "session", "preference"]
    content: str = Field(min_length=1, max_length=4000)
    weight: float = 1.0
    source: str | None = None


class SearchHit(BaseModel):
    kind: Literal["conversation", "message", "model", "canvas", "memory"]
    id: str
    title: str
    snippet: str
    score: float
    extra: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]
    took_ms: int
