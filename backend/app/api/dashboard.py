"""Dashboard endpoints (FR-16..19)."""
from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.dashboard.advice import get_advice
from app.dashboard.aggregator import aggregate, aggregate_kit
from app.database import get_session

log = logging.getLogger(__name__)
router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="templates")


def _get_redis(r: Request):
    return getattr(r.app.state, "redis", None)


def _get_llm(r: Request):
    return r.app.state.llm


@router.get("/dashboard/{material_id}/json")
async def dashboard_json(
    request: Request,
    material_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    stats = await aggregate(material_id, db)
    if not stats:
        raise HTTPException(status_code=404, detail="material_not_found")
    advice = await get_advice(
        stats, _get_llm(request), _get_redis(request),
        ttl=3600,
    )
    return {"stats": stats, "advice": advice}


@router.get("/dashboard/kit/{kit_id}/json")
async def dashboard_kit_json(
    request: Request,
    kit_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    stats = await aggregate_kit(kit_id, db)
    if not stats:
        raise HTTPException(status_code=404, detail="kit_not_found")
    advice = await get_advice(stats, _get_llm(request), _get_redis(request), ttl=3600)
    return {"stats": stats, "advice": advice}


@router.get("/dashboard/kit/{kit_id}", response_class=HTMLResponse)
async def dashboard_kit_page(
    request: Request,
    kit_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> HTMLResponse:
    stats = await aggregate_kit(kit_id, db)
    if not stats:
        raise HTTPException(status_code=404, detail="kit_not_found")
    advice = await get_advice(stats, _get_llm(request), _get_redis(request), ttl=3600)
    return templates.TemplateResponse(
        request=request,
        name="teacher/dashboard.html",
        context={"stats": stats, "advice": advice, "material_id": kit_id, "is_kit": True},
    )


@router.get("/dashboard/{material_id}", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    material_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> HTMLResponse:
    stats = await aggregate(material_id, db)
    if not stats:
        raise HTTPException(status_code=404, detail="material_not_found")
    advice = await get_advice(
        stats, _get_llm(request), _get_redis(request),
        ttl=3600,
    )
    return templates.TemplateResponse(
        request=request,
        name="teacher/dashboard.html",
        context={"stats": stats, "advice": advice, "material_id": material_id},
    )
