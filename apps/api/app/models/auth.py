"""Auth-related schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.models import PublicUser, Role, Status


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenPair(BaseModel):
    accessToken: str
    refreshToken: str
    expiresIn: int
    user: PublicUser


class RefreshIn(BaseModel):
    refreshToken: str


class PasswordChangeIn(BaseModel):
    oldPassword: str
    newPassword: str = Field(min_length=8, max_length=128)


class UserUpdateIn(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=32)
    avatar: str | None = None


class AdminUserUpdateIn(BaseModel):
    role: Role | None = None
    status: Status | None = None


class AuditLogOut(BaseModel):
    id: str
    actorId: str
    actorUsername: str | None = None
    action: str
    resource: str
    ipAddress: str | None = None
    userAgent: str | None = None
    timestamp: datetime


class NotificationOut(BaseModel):
    id: str
    title: str
    body: str
    read: bool
    createdAt: datetime
    kind: Literal["info", "warning", "success", "error"] = "info"


class UserListOut(BaseModel):
    items: list[PublicUser]
    total: int
    page: int
    size: int
