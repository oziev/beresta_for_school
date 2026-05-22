"""Aggregate student_sessions → per-task error rates and level distribution."""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Kit, Material, StudentSession

log = logging.getLogger(__name__)


async def aggregate(material_id: UUID, db: AsyncSession) -> dict:
    res = await db.execute(select(Material).where(Material.id == material_id))
    material = res.scalar_one_or_none()
    if not material:
        return {}

    tasks = material.tasks or []
    n_tasks = len(tasks)

    res2 = await db.execute(
        select(StudentSession).where(StudentSession.material_id == material_id)
    )
    sessions = res2.scalars().all()

    if not sessions:
        return {
            "session_count": 0,
            "errors_per_task": [],
            "level_distribution": {"1": 0, "2": 0, "3": 0},
            "avg_time": 0.0,
            "top_errors": [],
            "topic": material.topic,
            "grade": material.grade,
            "tasks": tasks,
        }

    # per-task counts
    task_total: list[int] = [0] * n_tasks
    task_wrong: list[int] = [0] * n_tasks
    task_time: list[float] = [0.0] * n_tasks
    level_dist: dict[str, int] = {"1": 0, "2": 0, "3": 0}

    for s in sessions:
        answers = s.answers or []
        for a in answers:
            idx = a.get("task_index")
            if idx is None or idx >= n_tasks:
                continue
            task_total[idx] += 1
            if not a.get("correct", True):
                task_wrong[idx] += 1
            task_time[idx] += float(a.get("time_spent", 0))
        fl = str(s.final_level or s.initial_level or 2)
        if fl in level_dist:
            level_dist[fl] += 1

    errors_per_task = []
    for i in range(n_tasks):
        total = task_total[i] or 1
        pct = round(task_wrong[i] / total * 100, 1)
        avg_t = round(task_time[i] / total, 1)
        errors_per_task.append({
            "task_index": i,
            "task_text": tasks[i].get("text", "")[:80],
            "wrong_count": task_wrong[i],
            "total_count": task_total[i],
            "error_pct": pct,
            "avg_time_sec": avg_t,
        })

    top_errors = sorted(errors_per_task, key=lambda x: x["error_pct"], reverse=True)[:3]

    all_times = [
        a.get("time_spent", 0)
        for s in sessions
        for a in (s.answers or [])
    ]
    avg_time = round(sum(all_times) / len(all_times), 1) if all_times else 0.0

    return {
        "session_count": len(sessions),
        "errors_per_task": errors_per_task,
        "level_distribution": level_dist,
        "avg_time": avg_time,
        "top_errors": top_errors,
        "topic": material.topic,
        "grade": material.grade,
        "tasks": tasks,
    }


async def aggregate_kit(kit_id: UUID, db: AsyncSession) -> dict:
    res = await db.execute(select(Kit).options(selectinload(Kit.items)).where(Kit.id == kit_id))
    kit = res.scalar_one_or_none()
    if not kit:
        return {}

    items = list(kit.items)
    n_items = len(items)
    res2 = await db.execute(select(StudentSession).where(StudentSession.kit_id == kit_id))
    sessions = res2.scalars().all()

    if not sessions:
        return {
            "session_count": 0,
            "errors_per_task": [],
            "level_distribution": {"1": 0, "2": 0, "3": 0},
            "avg_time": 0.0,
            "top_errors": [],
            "topic": kit.topic,
            "grade": kit.grade,
            "tasks": [{"text": item.title, "id": str(item.id)} for item in items],
            "kit_id": str(kit.id),
            "is_kit": True,
        }

    task_total = [0] * n_items
    task_wrong = [0] * n_items
    task_time = [0.0] * n_items
    level_dist = {"1": 0, "2": 0, "3": 0}

    for s in sessions:
        for a in s.answers or []:
            idx = a.get("task_index")
            if idx is None or idx >= n_items:
                continue
            task_total[idx] += 1
            if not a.get("correct", True):
                task_wrong[idx] += 1
            task_time[idx] += float(a.get("time_spent", 0))
        fl = str(s.final_level or s.initial_level or 2)
        if fl in level_dist:
            level_dist[fl] += 1

    errors_per_task = []
    for i, item in enumerate(items):
        total = task_total[i] or 1
        errors_per_task.append(
            {
                "task_index": i,
                "task_text": item.title[:80],
                "wrong_count": task_wrong[i],
                "total_count": task_total[i],
                "error_pct": round(task_wrong[i] / total * 100, 1),
                "avg_time_sec": round(task_time[i] / total, 1),
            }
        )

    all_times = [a.get("time_spent", 0) for s in sessions for a in (s.answers or [])]
    return {
        "session_count": len(sessions),
        "errors_per_task": errors_per_task,
        "level_distribution": level_dist,
        "avg_time": round(sum(all_times) / len(all_times), 1) if all_times else 0.0,
        "top_errors": sorted(errors_per_task, key=lambda x: x["error_pct"], reverse=True)[:3],
        "topic": kit.topic,
        "grade": kit.grade,
        "tasks": [{"text": item.title, "id": str(item.id)} for item in items],
        "kit_id": str(kit.id),
        "is_kit": True,
    }
