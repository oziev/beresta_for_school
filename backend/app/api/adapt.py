"""Adaptive student endpoints: QR, diagnose, answer (FR-10..15)."""
from __future__ import annotations

import base64
import io
import json
import logging
import uuid
from typing import Annotated, Any

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.adaptive.diagnostics import calculate_initial_level
from app.adaptive.engine import AdaptiveEngine
from app.config import get_settings
from app.database import get_session
from app.llm.cache import cache_get, cache_key_for_prompt, cache_set
from app.llm.client import GigaChatClient, GigaChatError
from app.llm.jsonutil import JSON_ONLY_SUFFIX, extract_json_object
from app.llm.prompts import prompt_diagnostic, prompt_hint, prompt_student_final_advice
from app.models import Kit, Material, StudentSession
from app.schemas import AdaptAnswerRequest, AdaptDiagnoseRequest

log = logging.getLogger(__name__)
router = APIRouter(tags=["adapt"])
templates = Jinja2Templates(directory="templates")
engine = AdaptiveEngine()


# ── helpers ─────

def _get_redis(request: Request):
    return getattr(request.app.state, "redis", None)


def _get_llm(request: Request) -> GigaChatClient:
    return request.app.state.llm


def _session_key(session_id: str) -> str:
    return f"adapt:session:{session_id}"


def _diag_key(material_id: str) -> str:
    return f"adapt:diag:{material_id}"


def _kit_tasks(kit: Kit) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for idx, item in enumerate(kit.items):
        levels = item.content_levels or {}
        for level_name, level_num in (("basic", 1), ("medium", 2), ("advanced", 3)):
            text = str(levels.get(level_name) or item.title)
            tasks.append(
                {
                    "text": text,
                    "options": None,
                    "correct": str((item.answer_key or {}).get(level_name) or (item.answer_key or {}).get("answer") or ""),
                    "time_limit_sec": 60,
                    "adaptive_level": level_num,
                    "type": item.type,
                    "kit_item_id": str(item.id),
                    "kit_item_index": idx,
                    "title": item.title,
                    "scaffolding_steps": item.example_mistakes or [],
                }
            )
    return tasks


def _diagnostic_fallback(topic: str) -> list[dict[str, Any]]:
    return [
        {"text": f"Что изучается в теме «{topic}»?", "options": ["Правило", "Случайность", "Игра", "Цвет"], "correct": 0, "time_sec": 15},
        {"text": "Выбери самый простой способ начать решение.", "options": ["Вспомнить правило", "Угадать", "Пропустить", "Списать"], "correct": 0, "time_sec": 15},
        {"text": "Что делать при ошибке?", "options": ["Проверить шаги", "Не исправлять", "Закрыть", "Удалить"], "correct": 0, "time_sec": 20},
    ]


async def _load_session(redis, session_id: str) -> dict[str, Any]:
    if redis is None:
        raise HTTPException(status_code=503, detail="redis_unavailable")
    raw = await redis.get(_session_key(session_id))
    if not raw:
        raise HTTPException(status_code=404, detail="session_not_found")
    return json.loads(raw)


async def _save_session(redis, session_id: str, data: dict[str, Any]) -> None:
    settings = get_settings()
    await redis.set(_session_key(session_id), json.dumps(data), ex=settings.redis_session_ttl_sec)


def _make_qr_b64(url: str) -> str:
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


async def _call_llm_json(
    llm: GigaChatClient,
    redis,
    prompt: str,
    ttl: int,
) -> dict[str, Any]:
    key = cache_key_for_prompt(prompt)
    raw = await cache_get(redis, key)
    if raw is None:
        try:
            raw = await llm.chat_completion(prompt)
        except (GigaChatError, Exception) as exc:
            log.error("LLM error: %s", exc)
            raise HTTPException(status_code=503, detail="llm_unavailable") from exc
        await cache_set(redis, key, raw, ttl)
    try:
        return extract_json_object(raw)
    except (ValueError, json.JSONDecodeError):
        repair = prompt + JSON_ONLY_SUFFIX
        rkey = cache_key_for_prompt(repair)
        raw2 = await cache_get(redis, rkey)
        if raw2 is None:
            try:
                raw2 = await llm.chat_completion(repair)
            except Exception as exc:
                log.error("LLM repair error: %s", exc)
                raise HTTPException(status_code=503, detail="llm_unavailable") from exc
            await cache_set(redis, rkey, raw2, ttl)
        return extract_json_object(raw2)


# ── routes ─────────────────────────────────────────────────────────────────────

@router.get("/adapt/{material_id}", response_class=HTMLResponse)
async def adapt_page(
    request: Request,
    material_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> HTMLResponse:
    res = await session.execute(select(Material).where(Material.id == material_id))
    material = res.scalar_one_or_none()
    if not material:
        raise HTTPException(status_code=404, detail="material_not_found")

    redis = _get_redis(request)
    settings = get_settings()
    llm = _get_llm(request)

    # Pre-generate 3 diagnostic questions and cache them
    diag_prompt = prompt_diagnostic(topic=material.topic, grade=material.grade)
    diag_key = _diag_key(str(material_id))
    diag_raw = await cache_get(redis, diag_key)
    if not diag_raw:
        diag_data = await _call_llm_json(llm, redis, diag_prompt, settings.llm_cache_ttl_sec)
        diag_raw = json.dumps(diag_data)
        await cache_set(redis, diag_key, diag_raw, settings.llm_cache_ttl_sec)
    diagnostic = json.loads(diag_raw).get("diagnostic", [])

    # Create Redis session
    session_id = str(uuid.uuid4())
    sess_data: dict[str, Any] = {
        "material_id": str(material_id),
        "topic": material.topic,
        "grade": material.grade,
        "tasks": list(material.tasks),
        "diagnostic": diagnostic,
        "phase": "diagnose",  # diagnose → main → finished
        "current_level": 2,
        "wrong_streak": 0,
        "answered": [],       # list of {task_index, answer, correct, time_spent}
        "diag_answers": [],
        "initial_level": None,
        "final_level": None,
    }
    await _save_session(redis, session_id, sess_data)

    base_url = str(request.base_url).rstrip("/")
    student_url = f"{base_url}/student/adapt/{material_id}"
    qr_b64 = _make_qr_b64(student_url)

    return templates.TemplateResponse(
        request=request,
        name="teacher/adapt_qr.html",
        context={
            "material": material,
            "session_id": session_id,
            "diagnostic": diagnostic,
            "qr_b64": qr_b64,
            "qr_url": student_url,
            "student_url": student_url,
        },
    )


@router.get("/student/adapt/{material_id}", response_class=HTMLResponse)
async def student_adapt_page(
    request: Request,
    material_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> HTMLResponse:
    """Страница ученика — тот же сеанс Redis, отдельный шаблон."""
    res = await session.execute(select(Material).where(Material.id == material_id))
    material = res.scalar_one_or_none()
    kit: Kit | None = None
    if material is None:
        kres = await session.execute(select(Kit).options(selectinload(Kit.items)).where(Kit.id == material_id))
        kit = kres.scalar_one_or_none()
    if material is None and kit is None:
        raise HTTPException(status_code=404, detail="material_or_kit_not_found")

    redis = _get_redis(request)
    settings = get_settings()
    llm = _get_llm(request)

    topic = material.topic if material else (kit.topic or "урок")
    grade = material.grade if material else kit.grade
    tasks = list(material.tasks) if material else _kit_tasks(kit)
    diag_prompt = prompt_diagnostic(topic=topic, grade=grade)
    diag_key = _diag_key(str(material_id))
    diag_raw = await cache_get(redis, diag_key)
    if not diag_raw:
        try:
            diag_data = await _call_llm_json(llm, redis, diag_prompt, settings.llm_cache_ttl_sec)
        except HTTPException:
            diag_data = {"diagnostic": _diagnostic_fallback(topic)}
        diag_raw = json.dumps(diag_data)
        await cache_set(redis, diag_key, diag_raw, settings.llm_cache_ttl_sec)
    diagnostic = json.loads(diag_raw).get("diagnostic", [])

    session_id = str(uuid.uuid4())
    sess_data: dict[str, Any] = {
        "material_id": str(material_id) if material else None,
        "kit_id": str(material_id) if kit else None,
        "topic": topic,
        "grade": grade,
        "tasks": tasks,
        "diagnostic": diagnostic,
        "phase": "diagnose",
        "current_level": 2,
        "wrong_streak": 0,
        "answered": [],
        "diag_answers": [],
        "initial_level": None,
        "final_level": None,
    }
    await _save_session(redis, session_id, sess_data)

    return templates.TemplateResponse(
        request=request,
        name="student/adapt.html",
        context={
            "material": material or kit,
            "session_id": session_id,
            "diagnostic": diagnostic,
            "tasks": tasks,
        },
    )


@router.post("/adapt/diagnose")
async def adapt_diagnose(
    request: Request,
    body: AdaptDiagnoseRequest,
) -> dict[str, Any]:
    redis = _get_redis(request)
    sess = await _load_session(redis, str(body.session_id))
    diag = sess.get("diagnostic", [])

    correct = 0
    total_time = 0.0
    results = []
    for i, ans in enumerate(body.answers):
        if i >= len(diag):
            break
        q = diag[i]
        is_correct = str(ans.get("answer")) == str(q.get("correct"))
        if is_correct:
            correct += 1
        total_time += float(ans.get("time_spent", q.get("time_sec", 15)))
        results.append({"index": i, "correct": is_correct})

    total = len(results) or 1
    avg_time = total_time / total
    max_time = float(sess.get("diagnostic", [{}])[0].get("time_sec", 45)) * 2

    level = calculate_initial_level(correct, total, avg_time, max_time=max_time)

    sess["initial_level"] = level
    sess["current_level"] = level
    sess["phase"] = "main"
    sess["diag_answers"] = results
    await _save_session(redis, str(body.session_id), sess)

    # Persist initial_level to DB (best-effort)
    db: AsyncSession = request.state.db if hasattr(request.state, "db") else None
    # We don't have DB dep in this route; we'll write on finish instead.

    return {"initial_level": level, "results": results}


@router.post("/adapt/answer")
async def adapt_answer(
    request: Request,
    body: AdaptAnswerRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    redis = _get_redis(request)
    llm = _get_llm(request)
    settings = get_settings()

    sess = await _load_session(redis, str(body.session_id))
    tasks = sess["tasks"]
    answered_indices = {a["task_index"] for a in sess["answered"]}

    if body.task_index >= len(tasks):
        raise HTTPException(status_code=400, detail="invalid_task_index")

    task = tasks[body.task_index]
    correct_val = task.get("correct")

    # Check correctness
    user_ans = str(body.answer).strip()
    if isinstance(correct_val, int):
        is_correct = str(correct_val) == user_ans
    elif correct_val:
        is_correct = str(correct_val).strip().lower() == user_ans.lower()
    else:
        is_correct = bool(user_ans)

    time_limit = float(task.get("time_limit_sec", 30))
    old_level = sess["current_level"]
    new_level = engine.process_answer(old_level, is_correct, body.time_spent, time_limit)

    wrong_streak = sess["wrong_streak"]
    wrong_streak = 0 if is_correct else wrong_streak + 1
    sess["wrong_streak"] = wrong_streak
    sess["current_level"] = new_level

    answered_indices.add(body.task_index)
    sess["answered"].append({
        "task_index": body.task_index,
        "answer": body.answer,
        "correct": is_correct,
        "time_spent": body.time_spent,
    })

    # Hint
    hint: str | None = None
    if engine.should_show_hint(wrong_streak):
        h_prompt = prompt_hint(
            task_text=task.get("text", ""),
            mistake_hint="типичная ошибка для этой темы",
        )
        h_data = await _call_llm_json(llm, redis, h_prompt, settings.llm_cache_ttl_sec)
        hint = h_data.get("hint")

    # Next task
    next_idx = engine.pick_next_task(tasks, new_level, answered_indices)
    is_finished = next_idx is None

    response: dict[str, Any] = {
        "correct": is_correct,
        "new_level": new_level,
        "hint": hint,
        "is_finished": is_finished,
        "next_task_index": next_idx,
        "next_task": tasks[next_idx] if next_idx is not None else None,
    }

    if is_finished:
        sess["phase"] = "finished"
        final_level = new_level
        sess["final_level"] = final_level
        correct_count = sum(1 for a in sess["answered"] if a["correct"])
        total_count = len(sess["answered"])

        advice_prompt = prompt_student_final_advice(
            topic=sess["topic"],
            correct_count=correct_count,
            total_count=total_count,
            initial_level=sess.get("initial_level") or 2,
            final_level=final_level,
        )
        advice_data = await _call_llm_json(llm, redis, advice_prompt, settings.llm_cache_ttl_sec)
        response["final_advice"] = advice_data.get("advice")
        sess["final_advice"] = response["final_advice"]
        response["final_level"] = final_level
        response["correct_count"] = correct_count
        response["total_count"] = total_count

        # Persist student session to DB
        try:
            student_sess = StudentSession(
                material_id=uuid.UUID(sess["material_id"]) if sess.get("material_id") else None,
                kit_id=uuid.UUID(sess["kit_id"]) if sess.get("kit_id") else None,
                initial_level=sess.get("initial_level"),
                final_level=final_level,
                answers=sess["answered"],
                hint_used_count=sum(1 for a in sess["answered"] if not a["correct"]),
            )
            db.add(student_sess)
            await db.commit()
        except Exception as exc:
            log.error("Failed to persist StudentSession: %s", exc)

    await _save_session(redis, str(body.session_id), sess)
    return response
