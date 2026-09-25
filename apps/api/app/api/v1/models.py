"""Model catalogue — a fixed list of the internal models.

No provider or key management here: these four models are always on and
never need credentials stored in Mongo. Display names come from
app.services.notrack, so branding stays in one place.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import current_user
from app.models.models import ModelOut
from app.services.notrack import NOTRACK_MODEL_DESCRIPTIONS, NOTRACK_MODELS

router = APIRouter(prefix="/models", tags=["models"])

_EPOCH = datetime(2024, 1, 1, tzinfo=UTC)


def _to_out(code: str) -> ModelOut:
    name = NOTRACK_MODELS[code]
    return ModelOut(
        id=code,
        name=name,
        temperature=0.7,
        maxTokens=32768,
        topP=1.0,
        enabled=True,
        description=NOTRACK_MODEL_DESCRIPTIONS.get(code),
        displayName=name,
        avatar=None,
        tags=["notrack"],
        createdAt=_EPOCH,
        updatedAt=_EPOCH,
    )


@router.get("", response_model=list[ModelOut])
async def list_models(user=Depends(current_user)) -> list[ModelOut]:
    return [_to_out(code) for code in NOTRACK_MODELS]


@router.get("/{model_id}", response_model=ModelOut)
async def get_model(model_id: str, user=Depends(current_user)) -> ModelOut:
    code = model_id.strip().upper()
    if code not in NOTRACK_MODELS:
        raise HTTPException(404, "model not found")
    return _to_out(code)
