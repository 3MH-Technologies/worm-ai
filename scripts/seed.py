"""Seed script: idempotent, useful for first-run dev data."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.core.config import get_settings
from app.core.security import hash_password
from app.db import mongo


async def main() -> None:
    await mongo.connect()
    now = datetime.now(tz=timezone.utc)
    s = get_settings()

    if await mongo.users().count_documents({"email": "admin@teteffd.hf.space"}) == 0:
        await mongo.users().insert_one({
            "username": "admin",
            "email": "admin@teteffd.hf.space",
            "passwordHash": hash_password("Admin123!"),
            "role": "superadmin",
            "status": "approved",
            "avatar": None,
            "createdAt": now,
            "updatedAt": now,
            "lastLogin": None,
            "failedLoginAttempts": 0,
            "lockedUntil": None,
        })
        print("seeded superadmin admin@teteffd.hf.space / Admin123!")

    if await mongo.users().count_documents({"email": "developer@teteffd.hf.space"}) == 0:
        await mongo.users().insert_one({
            "username": "developer",
            "email": "developer@teteffd.hf.space",
            "passwordHash": hash_password("Dev123!"),
            "role": "developer",
            "status": "approved",
            "avatar": None,
            "createdAt": now,
            "updatedAt": now,
            "lastLogin": None,
            "failedLoginAttempts": 0,
            "lockedUntil": None,
        })
        print("seeded developer developer@teteffd.hf.space / Dev123!")

    if await mongo.system_prompts().count_documents({"name": "worm-ai Default"}) == 0:
        await mongo.system_prompts().insert_one({
            "name": "worm-ai Default",
            "description": "Helpful, accurate, concise assistant.",
            "content": "You are worm-ai, a helpful, accurate, and concise AI assistant. "
                       "When unsure, say you don't know. Cite sources when relevant.",
            "tags": ["general"],
            "active": True,
            "currentVersion": 1,
            "versions": [{
                "version": 1, "content": "You are worm-ai, a helpful, accurate, and concise AI assistant. "
                                          "When unsure, say you don't know. Cite sources when relevant.",
                "changelog": "initial", "createdAt": now,
            }],
            "createdAt": now,
            "updatedAt": now,
        })
        print("seeded system prompt 'worm-ai Default'")

    print("done")
    await mongo.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
