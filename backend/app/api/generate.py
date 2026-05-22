"""POST /generate — full worksheet generation via GigaChat + Redis cache + DB."""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session
from app.llm.cache import cache_get, cache_key_for_prompt, cache_set
from app.llm.client import GigaChatClient, GigaChatError
from app.llm.jsonutil import JSON_ONLY_SUFFIX, extract_json_object
from app.llm.prompts import prompt_generate_sheet
from app.models import Material
from app.schemas import GenerateRequest, GenerateResponse, GenerationParams, Task

log = logging.getLogger(__name__)

router = APIRouter(tags=["generate"])


def get_llm(request: Request) -> GigaChatClient:
    return request.app.state.llm


def get_redis(request: Request):
    return getattr(request.app.state, "redis", None)


def _merge_params(req: GenerateRequest) -> GenerationParams:
    return req.generation_params or GenerationParams()


def _load_tasks_from_llm_text(raw: str, expected_count: int) -> list[Task]:
    data = extract_json_object(raw)
    items = data.get("tasks")
    if not isinstance(items, list):
        raise ValueError("JSON must contain a 'tasks' array")
    tasks = [Task.model_validate(x) for x in items]
    if len(tasks) != expected_count:
        raise ValueError(f"Expected {expected_count} tasks, got {len(tasks)}")
    return tasks


@router.post("/generate", response_model=GenerateResponse)
async def generate_worksheet(
    request: Request,
    body: GenerateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    llm: Annotated[GigaChatClient, Depends(get_llm)],
) -> GenerateResponse:
    params = _merge_params(body)
    teacher_profile: dict[str, Any] | None = None  # stage 6: подставить профиль

    prompt = prompt_generate_sheet(
        topic=body.topic,
        grade=body.grade,
        subject=body.subject,
        params=params,
        teacher_profile=teacher_profile,
    )

    redis = get_redis(request)
    settings = get_settings()
    cache_key = cache_key_for_prompt(prompt)

    raw: str | None = await cache_get(redis, cache_key)
    if raw is None:
        try:
            raw = await llm.chat_completion(prompt)
        except (GigaChatError, httpx.HTTPError) as exc:
            log.error("GigaChat completion failed: %s", exc)
            raise HTTPException(status_code=503, detail="llm_unavailable") from exc
        await cache_set(redis, cache_key, raw, settings.llm_cache_ttl_sec)

    # First parse attempt
    try:
        tasks = _load_tasks_from_llm_text(raw, params.task_count)
    except (ValueError, ValidationError, json.JSONDecodeError) as exc:
        log.error("Invalid JSON from LLM (first pass): %s", exc)
        tasks = None

    if tasks is None:
        repair_prompt = prompt + JSON_ONLY_SUFFIX + f"\n\nВ массиве tasks должно быть РОВНО {params.task_count} элементов."
        repair_key = cache_key_for_prompt(repair_prompt)
        raw2: str | None = await cache_get(redis, repair_key)
        if raw2 is None:
            try:
                raw2 = await llm.chat_completion(repair_prompt)
            except (GigaChatError, httpx.HTTPError) as exc:
                log.error("GigaChat completion failed on repair: %s", exc)
                raise HTTPException(status_code=503, detail="llm_unavailable") from exc
            await cache_set(redis, repair_key, raw2, settings.llm_cache_ttl_sec)
        try:
            tasks = _load_tasks_from_llm_text(raw2, params.task_count)
        except (ValueError, ValidationError, json.JSONDecodeError) as exc:
            log.error("Invalid JSON from LLM (repair pass): %s", exc)
            raise HTTPException(status_code=422, detail="llm_invalid_json") from exc

    material = Material(
        topic=body.topic.strip(),
        grade=body.grade,
        subject=body.subject.strip(),
        generation_params=params.model_dump(mode="json"),
        tasks=[t.model_dump(mode="json") for t in tasks],
        user_email=None,
        teacher_edited=False,
    )
    session.add(material)
    await session.commit()
    await session.refresh(material)

    return GenerateResponse(material_id=material.id, tasks=tasks)


@router.post("/generate-with-features", response_model=GenerateResponse)
async def generate_worksheet_with_features(
    request: Request,
    body: GenerateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    llm: Annotated[GigaChatClient, Depends(get_llm)],
) -> GenerateResponse:
    return await generate_worksheet(request=request, body=body, session=session, llm=llm)
