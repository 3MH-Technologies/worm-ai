"""Async MongoDB connection and index management."""

from __future__ import annotations

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, TEXT

from app.core.config import get_settings

log = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect() -> AsyncIOMotorDatabase:
    """Open a connection to MongoDB and ensure indexes exist."""
    global _client, _db
    settings = get_settings()
    _client = AsyncIOMotorClient(
        settings.mongo_uri,
        serverSelectionTimeoutMS=5000,
        uuidRepresentation="standard",
    )
    _db = _client[settings.mongo_db]
    try:
        await _db.command("ping")
        await _ensure_indexes(_db)
    except Exception:
        # Clean up so callers get an instant "Mongo not initialised" error
        # instead of hanging on a dead socket for every request.
        _client.close()
        _client = None
        _db = None
        raise
    log.info("mongo.connected db=%s", settings.mongo_db)
    return _db


async def disconnect() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None


def db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Mongo not initialised; call connect() first")
    return _db


def users():
    return db()["users"]


def conversations():
    return db()["conversations"]


def messages():
    return db()["messages"]


def models_col():
    return db()["models"]


def audit_logs():
    return db()["audit_logs"]


def notifications():
    return db()["notifications"]


def canvases():
    return db()["canvases"]


def canvas_versions():
    return db()["canvas_versions"]


def memories():
    return db()["memories"]


def folders():
    return db()["folders"]


def refresh_tokens():
    return db()["refresh_tokens"]


def devices():
    return db()["devices"]


def attachments():
    return db()["attachments"]


def password_resets():
    return db()["password_resets"]


def conversation_summaries():
    return db()["conversation_summaries"]


def errors_log():
    return db()["errors_log"]


async def _ensure_indexes(d: AsyncIOMotorDatabase) -> None:
    """Create all required indexes. Idempotent."""
    # users
    await d["users"].create_index([("email", ASCENDING)], unique=True)
    await d["users"].create_index([("username", ASCENDING)], unique=True)
    await d["users"].create_index([("status", ASCENDING)])

    # conversations
    await d["conversations"].create_index([("userId", ASCENDING), ("updatedAt", DESCENDING)])
    await d["conversations"].create_index([("userId", ASCENDING), ("folderId", ASCENDING)])
    await d["conversations"].create_index([("userId", ASCENDING), ("favorite", ASCENDING)])
    await d["conversations"].create_index(
        [("title", TEXT)],
        name="convo_text_idx",
        default_language="english",
    )

    # messages
    await d["messages"].create_index([("conversationId", ASCENDING), ("createdAt", ASCENDING)])
    await d["messages"].create_index(
        [("content", TEXT)],
        name="msg_text_idx",
        default_language="english",
    )

    # audit logs
    await d["audit_logs"].create_index([("actorId", ASCENDING), ("timestamp", DESCENDING)])
    await d["audit_logs"].create_index([("action", ASCENDING)])

    # notifications
    await d["notifications"].create_index([("userId", ASCENDING), ("createdAt", DESCENDING)])
    await d["notifications"].create_index([("userId", ASCENDING), ("read", ASCENDING)])

    # canvas
    await d["canvases"].create_index([("ownerId", ASCENDING), ("updatedAt", DESCENDING)])
    await d["canvases"].create_index([("type", ASCENDING)])
    await d["canvas_versions"].create_index(
        [("canvasId", ASCENDING), ("version", DESCENDING)],
        unique=True,
    )

    # memory
    await d["memories"].create_index([("userId", ASCENDING), ("kind", ASCENDING)])
    await d["memories"].create_index(
        [("content", TEXT)],
        name="memory_text_idx",
        default_language="english",
    )

    # folders
    await d["folders"].create_index([("userId", ASCENDING), ("name", ASCENDING)])

    # refresh tokens
    await d["refresh_tokens"].create_index([("token", ASCENDING)], unique=True)
    await d["refresh_tokens"].create_index([("userId", ASCENDING)])

    # devices
    await d["devices"].create_index([("userId", ASCENDING)])
    await d["devices"].create_index([("fingerprint", ASCENDING)])

    # attachments
    await d["attachments"].create_index([("userId", ASCENDING), ("createdAt", DESCENDING)])

    # password reset tokens
    await d["password_resets"].create_index([("tokenHash", ASCENDING)], unique=True)
    await d["password_resets"].create_index([("userId", ASCENDING)])
    await d["password_resets"].create_index([("expiresAt", ASCENDING)], expireAfterSeconds=0)

    # conversation summaries
    await d["conversation_summaries"].create_index(
        [("conversationId", ASCENDING), ("createdAt", DESCENDING)],
    )

    # error log
    await d["errors_log"].create_index([("createdAt", DESCENDING)])
    await d["errors_log"].create_index([("kind", ASCENDING), ("createdAt", DESCENDING)])


def now_ms() -> int:
    """Current time as epoch milliseconds."""
    import time
    return int(time.time() * 1000)


def oid(s: str) -> Any:
    from bson import ObjectId
    return ObjectId(s)
