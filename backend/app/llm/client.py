"""Async httpx client for GigaChat: OAuth token, chat/completions, retries, timeout."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time
import uuid
from typing import Any

import httpx

from app.config import Settings, get_settings

log = logging.getLogger(__name__)


class GigaChatError(Exception):
    """Raised when GigaChat returns an unexpected or empty response."""


def _authorization_basic(settings: Settings) -> str | None:
    if settings.gigachat_authorization_key:
        raw = settings.gigachat_authorization_key.strip()
        if raw.lower().startswith("basic "):
            return raw
        return f"Basic {raw}"
    if settings.gigachat_client_id and settings.gigachat_client_secret:
        token = base64.b64encode(
            f"{settings.gigachat_client_id}:{settings.gigachat_client_secret}".encode(),
        ).decode()
        return f"Basic {token}"
    return None


def _has_live_credentials(settings: Settings) -> bool:
    return _authorization_basic(settings) is not None


class GigaChatClient:
    """Minimal GigaChat REST wrapper (OAuth v2 + /chat/completions)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(self.settings.llm_timeout_sec))
        self._access_token: str | None = None
        self._access_token_expires_at: float = 0.0

    async def aclose(self) -> None:
        await self._http.aclose()

    def use_live_api(self) -> bool:
        if self.settings.beresta_llm_stub:
            return False
        return _has_live_credentials(self.settings)

    async def _fetch_token(self) -> str:
        auth = _authorization_basic(self.settings)
        if not auth:
            raise GigaChatError("GigaChat credentials are not configured")

        headers = {
            "Authorization": auth,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
        }
        data = {
            "scope": self.settings.gigachat_scope,
            "grant_type": "client_credentials",
        }
        resp = await self._http.post(self.settings.gigachat_oauth_url, headers=headers, data=data)
        resp.raise_for_status()
        payload = resp.json()
        token = payload.get("access_token")
        if not token:
            log.error("GigaChat OAuth response missing access_token: %s", payload)
            raise GigaChatError("OAuth response missing access_token")
        # `expires_at` is unix ms in GigaChat responses
        expires_at = payload.get("expires_at")
        if isinstance(expires_at, (int, float)):
            # GigaChat returns milliseconds since epoch
            self._access_token_expires_at = float(expires_at) / 1000.0
        else:
            self._access_token_expires_at = time.time() + 25 * 60
        self._access_token = token
        return token

    async def _ensure_token(self) -> str:
        if self._access_token and time.time() < self._access_token_expires_at - 30:
            return self._access_token
        return await self._fetch_token()

    async def chat_completion(self, user_prompt: str) -> str:
        """Return assistant text content (may contain JSON inside markdown fences)."""
        if not self.use_live_api():
            return self._stub_completion(user_prompt)

        token = await self._ensure_token()
        url = f"{self.settings.gigachat_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        body: dict[str, Any] = {
            "model": self.settings.gigachat_model,
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": 0.35,
        }

        last_exc: Exception | None = None
        delays = (0.5, 1.0, 2.0)
        for attempt, delay in enumerate([0.0, *delays], start=1):
            if delay:
                await asyncio.sleep(delay)
            try:
                resp = await self._http.post(url, headers=headers, json=body)
                if resp.status_code in (429, 500, 502, 503, 504):
                    log.error("GigaChat transient HTTP %s: %s", resp.status_code, resp.text[:500])
                    last_exc = GigaChatError(f"HTTP {resp.status_code}")
                    continue
                resp.raise_for_status()
                data = resp.json()
                choices = data.get("choices") or []
                if not choices:
                    log.error("GigaChat empty choices: %s", data)
                    raise GigaChatError("Empty choices in response")
                content = choices[0].get("message", {}).get("content")
                if not isinstance(content, str) or not content.strip():
                    log.error("GigaChat empty content: %s", data)
                    raise GigaChatError("Empty message content")
                return content
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                log.error("GigaChat transport/timeout error: %s", exc)
                last_exc = exc
            except httpx.HTTPStatusError as exc:
                log.error("GigaChat HTTP error: %s", exc)
                last_exc = exc

        assert last_exc is not None
        raise last_exc

    def _stub_completion(self, user_prompt: str) -> str:
        """Deterministic JSON for local runs when API keys are absent or stub mode is on."""
        # Very small heuristic: if prompt asks for single task JSON, return one task
        if '"text"' in user_prompt and "альтернативный вариант" in user_prompt:
            task = {
                "text": "Демо-задание (stub): вычислите 12 + 15.",
                "options": ["25", "27", "28", "30"],
                "correct": 1,
                "time_limit_sec": 30,
                "adaptive_level": 2,
                "type": "test",
            }
            return json.dumps(task, ensure_ascii=False)
        if "диагност" in user_prompt.lower():
            demo = {
                "diagnostic": [
                    {
                        "text": "Stub: что такое дробь?",
                        "options": ["часть целого", "только числитель", "только знаменатель", "целое число"],
                        "correct": 0,
                        "time_sec": 10,
                    },
                    {
                        "text": "Stub: сложите 1/2 и 1/4",
                        "options": ["1/6", "2/4", "3/4", "1"],
                        "correct": 2,
                        "time_sec": 15,
                    },
                    {
                        "text": "Stub: какая дробь больше: 3/5 или 2/3?",
                        "options": ["3/5", "2/3", "равны", "нельзя сравнить"],
                        "correct": 1,
                        "time_sec": 20,
                    },
                ]
            }
            return json.dumps(demo, ensure_ascii=False)
        if "совет учителю" in user_prompt.lower() or '"advice"' in user_prompt:
            return json.dumps({"advice": "Stub: повторите базовые определения и разберите 2 типовых ошибки на доске."}, ensure_ascii=False)
        if "методист" in user_prompt.lower() or "strengths" in user_prompt:
            return json.dumps(
                {
                    "strengths": "Stub: логичная последовательность заданий.",
                    "pitfalls": "Stub: путаница со знаменателем при сложении.",
                    "next_lesson": "Stub: визуализация на кругах и 5 минут устной работы.",
                    "time_estimate": "Stub: слабые 25 мин / средние 15 / сильные 10",
                },
                ensure_ascii=False,
            )
        if "анализируй" in user_prompt.lower() and "правок" in user_prompt.lower():
            return json.dumps(
                {
                    "preferred_difficulty": "medium",
                    "preferred_task_types": ["test", "problem"],
                    "avg_time_per_task": 45,
                    "language_style": "friendly",
                    "hates_topics": [],
                    "loves_visuals": True,
                    "hint_style": "example_first",
                },
                ensure_ascii=False,
            )
        if "подсказку" in user_prompt.lower() and '"hint"' in user_prompt:
            return json.dumps({"hint": "Stub: вспомните определение и проверьте знаменатель."}, ensure_ascii=False)
        if "персонализированный совет" in user_prompt.lower():
            return json.dumps({"advice": "Stub: повторите тему на простых числовых примерах."}, ensure_ascii=False)

        # Default: full sheet
        m = re.search(r"Сгенерируй\s+(\d+)\s+задан", user_prompt)
        n = int(m.group(1)) if m else 5
        n = max(3, min(10, n))
        tm = re.search(r"теме\s+\"([^\"]+)\"", user_prompt)
        topic = tm.group(1) if tm else "тема"
        tasks = []
        for i in range(n):
            tasks.append(
                {
                    "text": f"Stub {i + 1}: задание по теме «{topic}».",
                    "options": ["вариант A", "вариант B", "вариант C", "вариант D"],
                    "correct": i % 4,
                    "time_limit_sec": 30,
                    "adaptive_level": (i % 3) + 1,
                    "type": "test",
                },
            )
        return json.dumps({"tasks": tasks}, ensure_ascii=False)
