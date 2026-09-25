"""Integration test fixtures - requires MongoDB."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token, hash_password
from app.db import mongo


def pytest_configure(config):
    os.environ.setdefault("APP_ENV", "test")
    os.environ.setdefault("MONGO_DB", "wormgpt_test")
    os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-testing-only")
    os.environ.setdefault("RATE_LIMIT_PER_MIN", "10000")


@pytest_asyncio.fixture(autouse=True)
async def _clean():
    """Clean all collections before each test."""
    from app.core.config import get_settings

    get_settings()
    await mongo.connect()
    try:
        names = await mongo.db().list_collection_names()
        for name in names:
            if name.startswith("system."):
                continue
            try:
                await mongo.db()[name].delete_many({})
            except Exception:
                pass
    finally:
        await mongo.disconnect()


@pytest_asyncio.fixture
async def app():
    from app.main import app as _app

    yield _app


@pytest_asyncio.fixture
async def client(app) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _make_user(
    uid: str,
    status: str = "approved",
) -> dict[str, Any]:
    await mongo.connect()
    try:
        now = datetime.now(tz=timezone.utc)
        doc = {
            "_id": mongo.oid(uid),
            "username": f"user_{uid[-6:]}",
            "email": f"{uid[-6:]}@test.local",
            "passwordHash": hash_password("TestPass123!"),
            "status": status,
            "avatar": None,
            "createdAt": now,
            "updatedAt": now,
            "lastLogin": None,
            "failedLoginAttempts": 0,
            "lockedUntil": None,
        }
        await mongo.users().insert_one(doc)
        return {**doc, "_id": mongo.oid(uid)}
    finally:
        await mongo.disconnect()


@pytest_asyncio.fixture
async def regular_user() -> dict[str, Any]:
    return await _make_user("000000000000000000000001")


@pytest_asyncio.fixture
async def regular_user_token(regular_user) -> str:
    return create_access_token(sub=str(regular_user["_id"]))


@pytest_asyncio.fixture
async def second_user() -> dict[str, Any]:
    """A different regular user — used to verify ownership/IDOR checks."""
    return await _make_user("000000000000000000000007")


@pytest_asyncio.fixture
async def second_user_token(second_user) -> str:
    return create_access_token(sub=str(second_user["_id"]))


@pytest_asyncio.fixture
async def suspended_user() -> dict[str, Any]:
    return await _make_user("000000000000000000000005", "suspended")


@pytest_asyncio.fixture
async def suspended_user_token(suspended_user) -> str:
    return create_access_token(sub=str(suspended_user["_id"]))


@pytest_asyncio.fixture
async def rejected_user() -> dict[str, Any]:
    return await _make_user("000000000000000000000006", "rejected")


@pytest_asyncio.fixture
async def rejected_user_token(rejected_user) -> str:
    return create_access_token(sub=str(rejected_user["_id"]))
