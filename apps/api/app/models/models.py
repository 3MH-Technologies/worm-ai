"""Model catalogue schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ModelOut(BaseModel):
    """Public-facing model representation."""
    id: str
    name: str
    temperature: float
    maxTokens: int
    topP: float
    enabled: bool
    description: str | None = None
    displayName: str | None = None
    avatar: str | None = None
    tags: list[str]
    createdAt: datetime
    updatedAt: datetime
