"""POST /profile/train, GET /profile, POST /profile/reset (FR-24..26)."""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session
from app.teacher.profiler import count_edits, get_profile, reset_profile, train_profile

log = logging.getLogger(__name__)
router = APIRouter(tags=["profile"])


def _get_redis(r: Request):
    return getattr(r.app.state, "redis", None)


def _get_llm(r: Request):
    return r.app.state.llm


@router.post("/profile/train")
async def profile_train(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    settings = get_settings()
    profile_data = await train_profile(
        db, _get_llm(request), _get_redis(request), ttl=settings.llm_cache_ttl_sec
    )
    return {"profile": profile_data}


@router.get("/profile")
async def profile_get(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    tp = await get_profile(db)
    total = await count_edits(db)
    return {
        "profile": tp.profile if tp else None,
        "total_edits": total,
        "last_trained": tp.last_trained.isoformat() if tp and tp.last_trained else None,
        "enabled": tp.enabled if tp else True,
    }


@router.post("/profile/reset")
async def profile_reset(
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    await reset_profile(db)
    return {"success": True}
