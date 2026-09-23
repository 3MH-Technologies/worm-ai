"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    agent,
    attachments,
    auth,
    canvas,
    chat,
    health,
    memory,
    models,
    notifications,
    password_reset,
    research,
    search,
    security,
    summarize,
    system_prompts,
    web,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(password_reset.router)
api_router.include_router(models.router)
api_router.include_router(system_prompts.router)
api_router.include_router(chat.router)
api_router.include_router(summarize.router)
api_router.include_router(agent.router)
api_router.include_router(admin.router)
api_router.include_router(notifications.router)
api_router.include_router(memory.router)
api_router.include_router(search.router)
api_router.include_router(canvas.router)
api_router.include_router(research.router)
api_router.include_router(web.router)
api_router.include_router(attachments.router)
api_router.include_router(security.router)
