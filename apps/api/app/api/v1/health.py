from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "worm-ai",
        "credits": "© 3MH Technologies — https://3mh.pages.dev — t.me/j49_c",
    }


@router.get("/health/ready")
async def ready() -> dict:
    from app.cache import redis as redis_cache
    from app.db import mongo
    info: dict = {"mongo": "unknown", "redis": "unknown"}
    try:
        await mongo.db().command("ping")
        info["mongo"] = "ok"
    except Exception as e:
        info["mongo"] = f"error: {e}"
    try:
        await redis_cache.client().ping()
        info["redis"] = "ok"
    except Exception as e:
        info["redis"] = f"error: {e}"
    return info
