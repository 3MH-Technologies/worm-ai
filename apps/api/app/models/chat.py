"""Conversation and message schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["user", "assistant", "system", "tool"]


class MessageCreate(BaseModel):
    content: str = Field(default="", max_length=200_000)
    role: Role = "user"
    modelId: str | None = None
    attachments: list[dict[str, Any]] | None = None
    regenerate: bool = False
    parentId: str | None = None
    webSearch: bool = False
    canvas: bool = False


class MessageEdit(BaseModel):
    content: str = Field(min_length=1, max_length=200_000)


class MessageReaction(BaseModel):
    reaction: Literal["like", "dislike", "love", "laugh", "sad"]


class MessageOut(BaseModel):
    id: str
    conversationId: str
    role: Role
    content: str
    tokens: int | None = None
    model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    reaction: str | None = None
    parentId: str | None = None
    createdAt: datetime
    editedAt: datetime | None = None


class ConversationCreate(BaseModel):
    title: str | None = None
    modelId: str | None = None
    folderId: str | None = None
    mode: Literal["chat", "agent"] = "chat"


class ConversationUpdate(BaseModel):
    title: str | None = None
    folderId: str | None = None
    favorite: bool | None = None
    shared: bool | None = None


class ConversationOut(BaseModel):
    id: str
    userId: str
    title: str
    modelId: str | None = None
    mode: str = "chat"
    folderId: str | None = None
    favorite: bool = False
    shared: bool = False
    messageCount: int = 0
    lastMessageAt: datetime | None = None
    createdAt: datetime
    updatedAt: datetime


class ConversationWithMessages(ConversationOut):
    messages: list[MessageOut] = Field(default_factory=list)


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    color: str | None = None
    icon: str | None = None


class FolderOut(BaseModel):
    id: str
    userId: str
    name: str
    color: str | None = None
    icon: str | None = None
    conversationCount: int = 0
