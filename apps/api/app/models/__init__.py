"""Common schema fragments."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

PyObjectId = Annotated[str, Field(pattern=r"^[a-f\d]{24}$")]


class APIError(BaseModel):
    error: str
    detail: str | None = None
    code: str | None = None


class Page(BaseModel):
    model_config = ConfigDict(extra="ignore")
    page: int = 1
    size: int = 50


class TimestampMixin(BaseModel):
    createdAt: datetime | None = None
    updatedAt: datetime | None = None


Role = Literal["user", "moderator", "developer", "admin", "superadmin"]
Status = Literal["pending", "approved", "rejected", "suspended"]


class PublicUser(BaseModel):
    id: str
    username: str
    email: EmailStr
    role: Role
    status: Status
    avatar: str | None = None
    createdAt: datetime | None = None
    lastLogin: datetime | None = None
