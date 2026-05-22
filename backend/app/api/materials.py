"""Material CRUD, task regeneration (промпт №6), HTMX partials for inline editing."""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session
from app.llm.cache import cache_get, cache_key_for_prompt, cache_set
from app.llm.client import GigaChatClient, GigaChatError
from app.llm.jsonutil import JSON_ONLY_SUFFIX, extract_json_object
from app.llm.prompts import prompt_regenerate_task
from app.models import Material
from app.schemas import (
    GenerationParams,
    MaterialRead,
    MaterialUpdate,
    RegenerateTaskRequest,
    RegenerateTaskResponse,
    Task,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/materials", tags=["materials"])
task_router = APIRouter(tags=["materials"])
templates = Jinja2Templates(directory="templates")


def get_llm(request: Request) -> GigaChatClient:
    return request.app.state.llm


def get_redis(request: Request):
    return getattr(request.app.state, "redis", None)


async def _get_material_or_404(session: AsyncSession, material_id: UUID) -> Material:
    res = await session.execute(select(Material).where(Material.id == material_id))
    material = res.scalar_one_or_none()
    if material is None:
        raise HTTPException(status_code=404, detail="material_not_found")
    return material


def _task_from_payload(data: dict[str, Any]) -> Task:
    if "task" in data and isinstance(data["task"], dict):
        return Task.model_validate(data["task"])
    return Task.model_validate(data)


@router.get("/{material_id}/htmx/tasks/{task_index}/view", response_class=HTMLResponse)
async def htmx_task_view(
    request: Request,
    material_id: UUID,
    task_index: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> HTMLResponse:
    material = await _get_material_or_404(session, material_id)
    tasks_raw = list(material.tasks)
    if task_index < 0 or task_index >= len(tasks_raw):
        raise HTTPException(status_code=404, detail="task_index_out_of_range")
    task = Task.model_validate(tasks_raw[task_index])
    return templates.TemplateResponse(
        request=request,
        name="partials/task_view.html",
        context={"material_id": material_id, "idx": task_index, "task": task},
    )


@router.get("/{material_id}/htmx/tasks/{task_index}/edit", response_class=HTMLResponse)
async def htmx_task_edit(
    request: Request,
    material_id: UUID,
    task_index: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> HTMLResponse:
    material = await _get_material_or_404(session, material_id)
    tasks_raw = list(material.tasks)
    if task_index < 0 or task_index >= len(tasks_raw):
        raise HTTPException(status_code=404, detail="task_index_out_of_range")
    task = Task.model_validate(tasks_raw[task_index])
    options_text = "" if task.options is None else "\n".join(task.options)
    return templates.TemplateResponse(
        request=request,
        name="partials/task_edit.html",
        context={
            "material_id": material_id,
            "idx": task_index,
            "task": task,
            "options_text": options_text,
        },
    )


@router.post("/{material_id}/htmx/tasks/{task_index}", response_class=HTMLResponse)
async def htmx_task_save(
    request: Request,
    material_id: UUID,
    task_index: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    text: Annotated[str, Form()],
    task_type: Annotated[str, Form(alias="type")],
    correct: Annotated[str, Form()],
    time_limit_sec: Annotated[int, Form()],
    adaptive_level: Annotated[int, Form()],
    options_text: Annotated[str, Form()] = "",
) -> HTMLResponse:
    material = await _get_material_or_404(session, material_id)
    tasks_raw = list(material.tasks)
    if task_index < 0 or task_index >= len(tasks_raw):
        raise HTTPException(status_code=404, detail="task_index_out_of_range")

    opts = [ln.strip() for ln in options_text.splitlines() if ln.strip()]
    options_val: list[str] | None = opts if opts else None

    correct_val: int | str
    try:
        correct_val = int(correct)
    except ValueError:
        correct_val = correct

    updated = Task(
        text=text,
        type=task_type,  # type: ignore[arg-type]
        correct=correct_val,
        time_limit_sec=time_limit_sec,
        adaptive_level=adaptive_level,
        options=options_val,
    )

    tasks_raw[task_index] = updated.model_dump(mode="json")
    material.tasks = tasks_raw
    material.teacher_edited = True
    await session.commit()

    return templates.TemplateResponse(
        request=request,
        name="partials/task_view.html",
        context={"material_id": material_id, "idx": task_index, "task": updated},
    )


@router.get("/{material_id}", response_model=MaterialRead)
async def get_material(
    material_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MaterialRead:
    material = await _get_material_or_404(session, material_id)
    gp = None
    if material.generation_params is not None:
        gp = GenerationParams.model_validate(material.generation_params)
    return MaterialRead(
        id=material.id,
        topic=material.topic,
        grade=material.grade,
        subject=material.subject,
        generation_params=gp,
        tasks=[Task.model_validate(t) for t in material.tasks],
        created_at=material.created_at,
        teacher_edited=material.teacher_edited,
    )


@router.put("/{material_id}")
async def put_material(
    material_id: UUID,
    body: MaterialUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, bool]:
    material = await _get_material_or_404(session, material_id)
    material.tasks = [t.model_dump(mode="json") for t in body.tasks]
    material.teacher_edited = True
    await session.commit()
    return {"success": True}


@task_router.post("/generate/task", response_model=RegenerateTaskResponse)
async def regenerate_single_task(
    request: Request,
    body: RegenerateTaskRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    llm: Annotated[GigaChatClient, Depends(get_llm)],
) -> RegenerateTaskResponse:
    material = await _get_material_or_404(session, body.material_id)
    tasks_raw = list(material.tasks)
    if body.task_index < 0 or body.task_index >= len(tasks_raw):
        raise HTTPException(status_code=404, detail="task_index_out_of_range")

    original = Task.model_validate(tasks_raw[body.task_index])
    prompt = prompt_regenerate_task(
        original_task=original,
        topic=material.topic,
        grade=material.grade,
        feedback=body.feedback,
    )

    redis = get_redis(request)
    settings = get_settings()
    cache_key = cache_key_for_prompt(prompt)

    raw: str | None = await cache_get(redis, cache_key)
    if raw is None:
        try:
            raw = await llm.chat_completion(prompt)
        except (GigaChatError, httpx.HTTPError) as exc:
            log.error("GigaChat completion failed (task regen): %s", exc)
            raise HTTPException(status_code=503, detail="llm_unavailable") from exc
        await cache_set(redis, cache_key, raw, settings.llm_cache_ttl_sec)

    try:
        data = extract_json_object(raw)
        new_task = _task_from_payload(data)
    except (ValueError, ValidationError, json.JSONDecodeError) as exc:
        log.error("Invalid JSON from LLM (task regen): %s", exc)
        repair = prompt + JSON_ONLY_SUFFIX
        repair_key = cache_key_for_prompt(repair)
        try:
            raw2 = await llm.chat_completion(repair)
        except (GigaChatError, httpx.HTTPError) as exc2:
            log.error("GigaChat repair failed (task regen): %s", exc2)
            raise HTTPException(status_code=503, detail="llm_unavailable") from exc2
        await cache_set(redis, repair_key, raw2, settings.llm_cache_ttl_sec)
        try:
            data2 = extract_json_object(raw2)
            new_task = _task_from_payload(data2)
        except (ValueError, ValidationError, json.JSONDecodeError) as exc3:
            log.error("Invalid JSON from LLM after repair (task regen): %s", exc3)
            raise HTTPException(status_code=422, detail="llm_invalid_json") from exc3

    tasks_raw[body.task_index] = new_task.model_dump(mode="json")
    material.tasks = tasks_raw
    material.teacher_edited = True
    await session.commit()

    return RegenerateTaskResponse(task=new_task)
