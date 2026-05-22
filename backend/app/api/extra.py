"""Extra endpoints: PDF export, ungeneratable, reflection (FR-27..28, этап 7)."""
from __future__ import annotations

import json
import logging
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session
from app.export.pdf import render_pdf
from app.llm.cache import cache_get, cache_key_for_prompt, cache_set
from app.llm.client import GigaChatClient, GigaChatError
from app.llm.jsonutil import JSON_ONLY_SUFFIX, extract_json_object
from app.llm.prompts import prompt_methodological_reflection
from app.models import Material

log = logging.getLogger(__name__)
router = APIRouter(tags=["extra"])

UNGENERATABLE_TEXT = (
    "\n\n🔒 Рукописный элемент: нарисуй схему ручкой на бумаге "
    "и сфотографируй для проверки учителем."
)


def _get_redis(r: Request):
    return getattr(r.app.state, "redis", None)


def _get_llm(r: Request) -> GigaChatClient:
    return r.app.state.llm


@router.get("/export/pdf/{material_id}")
async def export_pdf(
    request: Request,
    material_id: uuid.UUID,
    mode: Literal["worksheet", "dashboard"] = "worksheet",
    template: str = "classic",  # ← ДОБАВЛЕНО
    db: Annotated[AsyncSession, Depends(get_session)] = None,
) -> Response:
    try:
        pdf_bytes = await render_pdf(material_id, mode, db, template_name=template)  # ← ИЗМЕНЕНО
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="beresta_{material_id}_{template}.pdf"'},
    )


@router.post("/materials/{material_id}/ungeneratable")
async def make_ungeneratable(
    material_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    res = await db.execute(select(Material).where(Material.id == material_id))
    material = res.scalar_one_or_none()
    if not material:
        raise HTTPException(status_code=404, detail="material_not_found")

    tasks = list(material.tasks)
    for t in tasks:
        if UNGENERATABLE_TEXT not in t.get("text", ""):
            t["text"] = t.get("text", "") + UNGENERATABLE_TEXT
    material.tasks = tasks
    material.teacher_edited = True
    await db.commit()
    return {"success": True, "tasks_updated": len(tasks)}


@router.get("/reflection/{material_id}")
async def reflection(
    request: Request,
    material_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    res = await db.execute(select(Material).where(Material.id == material_id))
    material = res.scalar_one_or_none()
    if not material:
        raise HTTPException(status_code=404, detail="material_not_found")

    llm = _get_llm(request)
    redis = _get_redis(request)
    settings = get_settings()

    prompt = prompt_methodological_reflection(topic=material.topic, grade=material.grade)
    key = cache_key_for_prompt(prompt, prefix="reflection")
    raw = await cache_get(redis, key)
    if raw is None:
        try:
            raw = await llm.chat_completion(prompt)
        except (GigaChatError, Exception) as exc:
            log.error("LLM reflection error: %s", exc)
            raise HTTPException(status_code=503, detail="llm_unavailable") from exc
        await cache_set(redis, key, raw, settings.llm_cache_ttl_sec)

    try:
        return extract_json_object(raw)
    except (ValueError, json.JSONDecodeError):
        repair = prompt + JSON_ONLY_SUFFIX
        rkey = cache_key_for_prompt(repair, prefix="reflection")
        raw2 = await cache_get(redis, rkey)
        if raw2 is None:
            try:
                raw2 = await llm.chat_completion(repair)
            except Exception as exc:
                log.error("LLM reflection repair error: %s", exc)
                raise HTTPException(status_code=503, detail="llm_unavailable") from exc
            await cache_set(redis, rkey, raw2, settings.llm_cache_ttl_sec)
        try:
            return extract_json_object(raw2)
        except Exception as exc:
            raise HTTPException(status_code=422, detail="llm_invalid_json") from exc