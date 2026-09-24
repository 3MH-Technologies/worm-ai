"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.cache import redis as redis_cache
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import CSRFMiddleware, RequestContextMiddleware, SecurityHeadersMiddleware
from app.core.security import hash_password
from app.db import mongo

configure_logging()
log = logging.getLogger("wormgpt.main")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # A fresh deploy (like a Hugging Face Space before its secrets are set)
    # must not crash-loop: log what's missing and keep serving so the UI loads
    # and /api/v1/health can report the problem.
    try:
        await mongo.connect()
        await _ensure_indexes()
        await _bootstrap_admin()
        log.info("worm-ai ready env=%s", settings.env)
    except Exception as e:
        log.error("database unavailable at boot: %s — set MONGO_URI in the environment", e)
    try:
        await redis_cache.connect()
    except Exception as e:
        log.warning("cache unavailable at boot: %s — set REDIS_URL in the environment", e)
    yield
    await mongo.disconnect()
    await redis_cache.disconnect()


async def _ensure_indexes() -> None:
    """Safety net: ensure indexes exist even if mongo.connect skipped them."""
    from app.db import mongo
    from app.db.mongo import _ensure_indexes as _db_ensure
    await _db_ensure(mongo.db())


async def _bootstrap_admin() -> None:
    """Seed a fresh install only: never modify accounts that already exist.

    Runs exclusively when the ``users`` collection is completely empty.
    Existing admins keep their UI-changed passwords across restarts (the
    old behaviour silently reset them from env on every boot), and no
    account with hardcoded credentials is ever created — new users go
    through registration + admin approval.
    """
    now = datetime.now(tz=UTC)
    created = 0

    if await mongo.users().find_one({}, projection={"_id": 1}) is None:
        await mongo.users().insert_one({
            "username": settings.bootstrap_admin_username,
            "email": settings.bootstrap_admin_email.lower(),
            "passwordHash": hash_password(settings.bootstrap_admin_password),
            "role": "superadmin",
            "status": "approved",
            "avatar": None,
            "createdAt": now,
            "updatedAt": now,
            "lastLogin": None,
            "failedLoginAttempts": 0,
            "lockedUntil": None,
        })
        log.info("bootstrap admin created: %s", settings.bootstrap_admin_email.lower())
        created += 1

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
                "version": 1,
                "content": "You are worm-ai, a helpful, accurate, and concise AI assistant. "
                           "When unsure, say you don't know. Cite sources when relevant.",
                "changelog": "initial",
                "createdAt": now,
            }],
            "createdAt": now,
            "updatedAt": now,
        })
        log.info("bootstrap system prompt created")
        created += 1

    if created:
        log.info("bootstrap complete: %d items created", created)


app = FastAPI(
    title="worm-ai API",
    version="0.1.0",
    description="Backend for the worm-ai chat platform. © 3MH Technologies — https://3mh.pages.dev",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.app_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(CSRFMiddleware)

app.include_router(api_router)


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {
        "service": "worm-ai",
        "version": "0.1.0",
        "docs": "/api/docs",
        "credits": "© 3MH Technologies — https://3mh.pages.dev — t.me/j49_c",
    }


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    rid = getattr(request.state, "request_id", None)
    log.exception("unhandled rid=%s err=%s", rid, exc)
    # best-effort persistence so admins can see the most recent server errors
    try:
        from datetime import datetime

        from app.db import mongo as _mongo
        await _mongo.errors_log().insert_one({
            "kind": "server",
            "message": f"{type(exc).__name__}: {exc}"[:1000],
            "path": str(request.url.path),
            "method": request.method,
            "status": 500,
            "actorId": None,
            "requestId": rid,
            "userAgent": request.headers.get("user-agent"),
            "createdAt": datetime.now(tz=UTC),
        })
    except Exception:
        pass
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail, "requestId": rid},
        )
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "requestId": rid},
    )
