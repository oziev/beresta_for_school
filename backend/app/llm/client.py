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
        # Отключаем проверку SSL для локальной разработки (самоподписанный сертификат GigaChat)
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(self.settings.llm_timeout_sec),
            verify=False  # ← ДЛЯ САМОПОДПИСАННОГО СЕРТИФИКАТА GigaChat
        )
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
        
        # Используем отдельный клиент с verify=False для OAuth запроса
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.post(
                self.settings.gigachat_oauth_url, 
                headers=headers, 
                data=data
            )
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
        
        # System prompt для стабильного JSON
        system_prompt = """Ты — ИИ-ассистент учителя.
ПРАВИЛА:
1. Возвращай ТОЛЬКО валидный JSON
2. Без пояснений, без markdown, без ```json
3. Не используй общие фразы типа "базовый вариант материала"
4. Каждое задание должно быть конкретным и содержательным
5. Начинай с { и заканчивай }"""
        
        body: dict[str, Any] = {
            "model": self.settings.gigachat_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3,  # понижено для стабильности JSON
            "max_tokens": 2500,
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
                
                log.debug(f"LLM response length: {len(content)} chars")
                return content
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                log.error("GigaChat transport/timeout error (attempt %d): %s", attempt, exc)
                last_exc = exc
            except httpx.HTTPStatusError as exc:
                log.error("GigaChat HTTP error (attempt %d): %s", attempt, exc)
                last_exc = exc

        assert last_exc is not None
        raise last_exc

    def _stub_completion(self, user_prompt: str) -> str:
        """Deterministic JSON for local runs when API keys are absent or stub mode is on."""
        prompt_lower = user_prompt.lower()
        
        # Литература
        if "литература" in prompt_lower or "литератур" in prompt_lower:
            if "онегин" in prompt_lower or "пушкин" in prompt_lower:
                return json.dumps({
                    "tasks": [
                        {
                            "text": "Назови главного героя романа 'Евгений Онегин'. Какие черты его характера проявляются в первой главе?",
                            "options": None,
                            "correct": "Евгений Онегин, разочарование, скука, эгоизм",
                            "time_limit_sec": 60,
                            "adaptive_level": 1,
                            "type": "open"
                        },
                        {
                            "text": "Почему Онегин отверг любовь Татьяны? Приведи 2 причины из текста.",
                            "options": None,
                            "correct": "1) Боязнь семейной жизни, 2) Ценил свободу, 3) Пресыщенность",
                            "time_limit_sec": 90,
                            "adaptive_level": 2,
                            "type": "open"
                        },
                        {
                            "text": "Сравни образы Онегина и Ленского. В чём их противопоставление помогает раскрыть замысел Пушкина?",
                            "options": None,
                            "correct": "Онегин — 'лишний человек', Ленский — романтик. Их дуэль показывает трагедию поколения",
                            "time_limit_sec": 120,
                            "adaptive_level": 3,
                            "type": "open"
                        }
                    ]
                }, ensure_ascii=False)
            return json.dumps({
                "tasks": [
                    {
                        "text": "Назови автора и главного героя произведения.",
                        "options": None,
                        "correct": "Ответ должен содержать имя автора и героя",
                        "time_limit_sec": 45,
                        "adaptive_level": 1,
                        "type": "open"
                    },
                    {
                        "text": "Какая основная проблема поднимается в произведении? Приведи пример из текста.",
                        "options": None,
                        "correct": "Проблема + цитата/пример",
                        "time_limit_sec": 90,
                        "adaptive_level": 2,
                        "type": "open"
                    },
                    {
                        "text": "Проанализируй образ главного героя. Какие средства художественной выразительности использует автор?",
                        "options": None,
                        "correct": "Анализ с примерами тропов и фигур",
                        "time_limit_sec": 120,
                        "adaptive_level": 3,
                        "type": "open"
                    }
                ]
            }, ensure_ascii=False)
        
        # Генерация заданий (общий случай)
        if "сгенерируй" in prompt_lower and "заданий" in prompt_lower:
            m = re.search(r"Сгенерируй\s+(\d+)\s+задан", user_prompt)
            n = int(m.group(1)) if m else 5
            n = max(3, min(10, n))
            tm = re.search(r"теме\s+\"([^\"]+)\"", user_prompt)
            topic = tm.group(1) if tm else "тема"
            tasks = []
            for i in range(n):
                level = (i % 3) + 1
                if level == 1:
                    text = f"Задание {i+1} (базовый): Что такое {topic}? Приведи определение."
                elif level == 2:
                    text = f"Задание {i+1} (средний): Объясни, как применять {topic} на практике. Приведи пример."
                else:
                    text = f"Задание {i+1} (продвинутый): Проанализируй {topic}. В чём его значение? Приведи аргументы."
                tasks.append({
                    "text": text,
                    "options": None,
                    "correct": "Развёрнутый ответ",
                    "time_limit_sec": 30 + i * 10,
                    "adaptive_level": level,
                    "type": "open" if level > 1 else "test",
                })
            return json.dumps({"tasks": tasks}, ensure_ascii=False)
        
        # Диагностика
        if "диагност" in prompt_lower:
            return json.dumps({
                "diagnostic": [
                    {"text": "Что вы уже знаете по этой теме? Напишите 2-3 предложения.", "options": None, "correct": "Любой связный ответ", "time_sec": 30},
                    {"text": "Какие вопросы у вас возникают при изучении этой темы?", "options": None, "correct": "Любой содержательный вопрос", "time_sec": 30},
                    {"text": "Что бы вы хотели узнать сегодня на уроке?", "options": None, "correct": "Любая учебная цель", "time_sec": 30}
                ]
            }, ensure_ascii=False)
        
        # Совет учителю
        if "совет" in prompt_lower and "учителю" in prompt_lower:
            return json.dumps({
                "advice": "Рекомендуется начать с повторения базовых понятий, затем перейти к практическим заданиям. Уделите внимание типичным ошибкам."
            }, ensure_ascii=False)
        
        # Методическая рефлексия
        if "методист" in prompt_lower or "рефлексия" in prompt_lower:
            return json.dumps({
                "strengths": "Задания охватывают ключевые аспекты темы, есть дифференциация по сложности.",
                "pitfalls": "Ученики могут путать основные понятия. Рекомендуется добавить визуальные опоры.",
                "next_lesson": "Закрепить материал на практических примерах, добавить работу в парах.",
                "time_estimate": "Слабые: 25 мин, Средние: 15 мин, Сильные: 10 мин"
            }, ensure_ascii=False)
        
        # Для комплекта раздаток
        if "комплект" in prompt_lower or "kit" in prompt_lower:
            return json.dumps({
                "items": [
                    {
                        "stage_name": "Актуализация знаний",
                        "type": "cards",
                        "title": "Карточки для разминки",
                        "content_levels": {
                            "basic": "Что такое [тема]? Дай определение.",
                            "medium": "Приведи пример использования [темы].",
                            "advanced": "Сравни [тему] с похожими понятиями. В чём разница?"
                        },
                        "complexity_level": 2,
                        "teacher_notes": "Обрати внимание на понимание базовых определений",
                        "answer_key": {"basic": "Определение", "medium": "Пример", "advanced": "Сравнение"}
                    }
                ]
            }, ensure_ascii=False)
        
        # Подсказка
        if "подсказк" in prompt_lower and "hint" in prompt_lower:
            return json.dumps({"hint": "Вспомните основное правило по этой теме."}, ensure_ascii=False)
        
        # Финальный совет ученику
        if "совет" in prompt_lower and "ученик" in prompt_lower:
            return json.dumps({"advice": "Повторите основные определения и выполните несколько практических заданий."}, ensure_ascii=False)
        
        # Default fallback
        return json.dumps({
            "tasks": [
                {
                    "text": "Демо-задание: объясните основную идею темы.",
                    "options": None,
                    "correct": "Развёрнутый ответ",
                    "time_limit_sec": 60,
                    "adaptive_level": 2,
                    "type": "open"
                }
            ]
        }, ensure_ascii=False)