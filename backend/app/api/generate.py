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
from app.llm.jsonutil import (
    JSON_ONLY_SUFFIX,
    extract_json_object,
    sanitize_latex,
    validate_tasks_response,
)
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


def _decode_unicode_escape(obj: Any) -> Any:
    """Рекурсивно декодирует unicode-escape последовательности в читаемый текст."""
    if isinstance(obj, dict):
        return {k: _decode_unicode_escape(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decode_unicode_escape(i) for i in obj]
    if isinstance(obj, str):
        # Если строка содержит \u, декодируем в русский текст
        if "\\u" in obj:
            try:
                return obj.encode("utf-8").decode("unicode-escape")
            except (UnicodeDecodeError, UnicodeEncodeError):
                return obj
        return obj
    return obj


def _load_tasks_from_llm_text(raw: str, expected_count: int) -> list[Task]:
    """Извлекает, валидирует и декодирует задания из ответа LLM."""
    data = extract_json_object(raw)
    data = _decode_unicode_escape(data)
    tasks = validate_tasks_response(data, expected_count)
    tasks = sanitize_latex(tasks)
    return [Task.model_validate(task) for task in tasks]


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
        log.warning("Invalid JSON from LLM (first pass): %s", exc)
        tasks = None

    # Repair attempt if first parse failed
    if tasks is None:
        repair_prompt = (
            prompt
            + JSON_ONLY_SUFFIX
            + f"\n\n⚠️ В массиве tasks должно быть РОВНО {params.task_count} элементов."
            + "\n❌ ЗАПРЕЩЕНО использовать общие фразы: 'базовый вариант материала', 'средний вариант материала', 'простые вопросы по теме'."
            + "\n✅ Каждое задание должно быть конкретным и содержательным."
        )
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

    # Final validation
    if not tasks or len(tasks) < params.task_count // 2:
        log.error("Too few tasks generated: got %d, expected %d", len(tasks) if tasks else 0, params.task_count)
        raise HTTPException(status_code=422, detail="not_enough_tasks_generated")

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

    # Декодируем ответ для API (чтобы учитель видел русский текст, а не \uXXXX)
    response_tasks = _decode_unicode_escape([t.model_dump(mode="json") for t in tasks])

    return GenerateResponse(material_id=material.id, tasks=response_tasks)


@router.post("/generate-with-features", response_model=GenerateResponse)
async def generate_worksheet_with_features(
    request: Request,
    body: GenerateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    llm: Annotated[GigaChatClient, Depends(get_llm)],
) -> GenerateResponse:
    return await generate_worksheet(request=request, body=body, session=session, llm=llm)