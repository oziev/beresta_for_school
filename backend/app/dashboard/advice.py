"""Generate AI advice for teacher dashboard (prompt #3)."""
from __future__ import annotations

import json
import logging

from app.llm.cache import cache_get, cache_key_for_prompt, cache_set
from app.llm.client import GigaChatClient, GigaChatError
from app.llm.jsonutil import JSON_ONLY_SUFFIX, extract_json_object
from app.llm.prompts import prompt_dashboard_advice

log = logging.getLogger(__name__)


def _stats_text(stats: dict) -> str:
    lines = []
    for e in stats.get("errors_per_task", []):
        lines.append(
            f"Задание {e['task_index']+1}: {e['error_pct']}% ошибок "
            f"(тип: {stats['tasks'][e['task_index']].get('type','?')})"
        )
    return "\n".join(lines) or "нет данных"


async def get_advice(
    stats: dict,
    llm: GigaChatClient,
    redis,
    ttl: int = 3600,
) -> str:
    if not stats.get("session_count"):
        return "Пока нет данных о сессиях учеников."

    prompt = prompt_dashboard_advice(
        topic=stats.get("topic", ""),
        grade=stats.get("grade", 0),
        statistics=_stats_text(stats),
    )
    key = cache_key_for_prompt(prompt, prefix="advice")
    raw = await cache_get(redis, key)
    if raw is None:
        try:
            raw = await llm.chat_completion(prompt)
        except (GigaChatError, Exception) as exc:
            log.error("LLM advice error: %s", exc)
            return "Не удалось получить совет ИИ."
        await cache_set(redis, key, raw, ttl)
    try:
        data = extract_json_object(raw)
        return data.get("advice", "")
    except (ValueError, json.JSONDecodeError):
        repair = prompt + JSON_ONLY_SUFFIX
        rkey = cache_key_for_prompt(repair, prefix="advice")
        raw2 = await cache_get(redis, rkey)
        if raw2 is None:
            try:
                raw2 = await llm.chat_completion(repair)
            except Exception as exc:
                log.error("LLM advice repair error: %s", exc)
                return "Не удалось получить совет ИИ."
            await cache_set(redis, rkey, raw2, ttl)
        try:
            return extract_json_object(raw2).get("advice", "")
        except Exception:
            return ""
