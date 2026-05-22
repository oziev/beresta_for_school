"""Collect teacher edits → build virtual twin profile via LLM (FR-23..26)."""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.cache import cache_key_for_prompt, cache_set
from app.llm.client import GigaChatClient, GigaChatError
from app.llm.jsonutil import JSON_ONLY_SUFFIX, extract_json_object
from app.llm.prompts import prompt_train_teacher_twin
from app.models import TeacherEdit, TeacherProfile

log = logging.getLogger(__name__)

DEMO_EMAIL = "demo@beresta.local"


async def count_edits(db: AsyncSession, user_email: str = DEMO_EMAIL) -> int:
    res = await db.execute(
        select(TeacherEdit).where(TeacherEdit.user_email == user_email)
    )
    return len(res.scalars().all())


async def train_profile(
    db: AsyncSession,
    llm: GigaChatClient,
    redis,
    user_email: str = DEMO_EMAIL,
    ttl: int = 3600,
) -> dict[str, Any]:
    res = await db.execute(
        select(TeacherEdit)
        .where(TeacherEdit.user_email == user_email)
        .order_by(TeacherEdit.created_at.desc())
        .limit(100)
    )
    edits = res.scalars().all()

    if not edits:
        return {}

    samples_lines = []
    deleted_creative = 0
    times: list[int] = []
    type_counter: Counter = Counter()
    topic_counter: Counter = Counter()

    for e in edits:
        if e.original_text and e.edited_text:
            samples_lines.append(f"• «{e.original_text[:60]}» → «{e.edited_text[:60]}»")
        if e.edit_type == "delete" and e.original_text and "creative" in (e.original_text or "").lower():
            deleted_creative += 1
        if e.edit_type:
            type_counter[e.edit_type] += 1

    prompt = prompt_train_teacher_twin(
        count=len(edits),
        samples="\n".join(samples_lines[:10]),
        deleted_creative=deleted_creative,
        avg_time=45,
        frequent_type=type_counter.most_common(1)[0][0] if type_counter else "edit",
        frequent_topic="неизвестно",
    )

    key = cache_key_for_prompt(prompt, prefix="profile")
    raw = None
    try:
        raw = await llm.chat_completion(prompt)
    except (GigaChatError, Exception) as exc:
        log.error("LLM profile training error: %s", exc)
        return {}

    if redis:
        await cache_set(redis, key, raw, ttl)

    try:
        profile_data = extract_json_object(raw)
    except (ValueError, json.JSONDecodeError):
        repair = prompt + JSON_ONLY_SUFFIX
        try:
            raw2 = await llm.chat_completion(repair)
            profile_data = extract_json_object(raw2)
        except Exception as exc:
            log.error("LLM profile repair failed: %s", exc)
            return {}

    # Upsert teacher profile
    res2 = await db.execute(
        select(TeacherProfile).where(TeacherProfile.user_email == user_email)
    )
    tp = res2.scalar_one_or_none()
    if tp:
        tp.profile = profile_data
        tp.total_edits = len(edits)
        tp.last_trained = datetime.now(timezone.utc)
    else:
        tp = TeacherProfile(
            user_email=user_email,
            profile=profile_data,
            total_edits=len(edits),
            last_trained=datetime.now(timezone.utc),
            enabled=True,
        )
        db.add(tp)
    await db.commit()
    return profile_data


async def get_profile(
    db: AsyncSession,
    user_email: str = DEMO_EMAIL,
) -> TeacherProfile | None:
    res = await db.execute(
        select(TeacherProfile).where(TeacherProfile.user_email == user_email)
    )
    return res.scalar_one_or_none()


async def reset_profile(
    db: AsyncSession,
    user_email: str = DEMO_EMAIL,
) -> None:
    res = await db.execute(
        select(TeacherProfile).where(TeacherProfile.user_email == user_email)
    )
    tp = res.scalar_one_or_none()
    if tp:
        tp.profile = None
        tp.total_edits = 0
        tp.last_trained = None
        await db.commit()


async def log_edit(
    db: AsyncSession,
    material_id,
    original_text: str | None,
    edited_text: str | None,
    edit_type: str,
    task_index: int | None = None,
    user_email: str = DEMO_EMAIL,
) -> None:
    # Ensure demo user exists
    from app.models import User
    from sqlalchemy import select as sa_select
    res = await db.execute(sa_select(User).where(User.email == user_email))
    if not res.scalar_one_or_none():
        db.add(User(email=user_email, password_hash=None))
        await db.flush()

    edit = TeacherEdit(
        user_email=user_email,
        material_id=material_id,
        original_text=original_text,
        edited_text=edited_text,
        edit_type=edit_type,
        task_index=task_index,
    )
    db.add(edit)
    await db.commit()
