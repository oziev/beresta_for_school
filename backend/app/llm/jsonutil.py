"""Extract JSON objects from LLM text (markdown fences, noisy prefixes, validation)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

log = logging.getLogger(__name__)


def extract_json_object(raw: str) -> dict[str, Any]:
    """
    Извлекает JSON из ответа LLM.
    Поддерживает:
    - markdown-блоки ```json ... ```
    - текст до и после JSON
    - JSON в кавычках
    - очистку от BOM и спецсимволов
    """
    if not raw or not raw.strip():
        raise ValueError("Empty LLM response")
    
    text = raw.strip()
    
    # Удаляем BOM и невидимые символы
    text = text.lstrip('\ufeff')
    
    # Способ 1: ищем в markdown-блоках
    if "```" in text:
        parts = text.split("```")
        for i, chunk in enumerate(parts):
            chunk = chunk.strip()
            if not chunk:
                continue
            # Удаляем "json" после открывающего блока
            if i > 0 and chunk.lower().startswith("json"):
                chunk = chunk[4:].lstrip()
            # Проверяем, что это JSON
            if chunk.startswith("{") and chunk.endswith("}"):
                try:
                    return json.loads(chunk)
                except json.JSONDecodeError:
                    continue
            if chunk.startswith("[") and chunk.endswith("]"):
                try:
                    result = json.loads(chunk)
                    if isinstance(result, list):
                        # Оборачиваем массив в объект с ключом tasks
                        return {"tasks": result}
                except json.JSONDecodeError:
                    continue
    
    # Способ 2: ищем первый { и последний }
    start = text.find("{")
    end = text.rfind("}")
    
    if start == -1 or end == -1 or end <= start:
        # Способ 3: ищем массив [ ... ]
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                result = json.loads(text[start:end + 1])
                if isinstance(result, list):
                    return {"tasks": result}
            except json.JSONDecodeError:
                pass
        raise ValueError(f"No JSON object found in: {text[:300]}")
    
    json_str = text[start:end + 1]
    
    # Очищаем JSON строку от проблемных символов
    json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_str)
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        log.error(f"JSON decode error: {e}")
        log.debug(f"Failed JSON string: {json_str[:500]}")
        raise ValueError(f"Invalid JSON: {e}") from e


def extract_json_array(raw: str) -> list[Any]:
    """Извлекает JSON массив из ответа LLM."""
    result = extract_json_object(raw)
    if "tasks" in result and isinstance(result["tasks"], list):
        return result["tasks"]
    if isinstance(result, list):
        return result
    raise ValueError("Response is not an array and has no 'tasks' array")


def sanitize_llm_response(raw: str) -> str:
    """Очищает ответ LLM от пояснений, оставляя только потенциальный JSON."""
    # Удаляем markdown
    raw = re.sub(r'```json\s*', '', raw)
    raw = re.sub(r'```\s*', '', raw)
    
    # Удаляем фразы типа "Вот ваш JSON:" или "Ответ:"
    raw = re.sub(r'^(?:вот|ответ|json|результат|результаты)\s*:?\s*', '', raw, flags=re.IGNORECASE)
    
    return raw.strip()


def validate_tasks_response(data: dict[str, Any], expected_count: int) -> list[dict[str, Any]]:
    """Валидирует ответ LLM с заданиями и добавляет default значения."""
    tasks = data.get("tasks")
    if not tasks:
        raise ValueError("No 'tasks' field in response")
    
    if not isinstance(tasks, list):
        raise ValueError("'tasks' is not an array")
    
    if len(tasks) < expected_count:
        log.warning(f"Expected {expected_count} tasks, got {len(tasks)}")
    
    validated = []
    for i, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise ValueError(f"Task {i} is not an object")
        
        # Обязательное поле
        if "text" not in task or not task["text"]:
            raise ValueError(f"Task {i} missing 'text'")
        
        # Для тестов проверяем options и correct
        if task.get("type") == "test" or ("options" in task and task["options"]):
            if "options" not in task or not task["options"]:
                task["options"] = ["Вариант A", "Вариант B", "Вариант C", "Вариант D"]
            if "correct" not in task:
                task["correct"] = 0
            # Нормализуем correct (индекс)
            if isinstance(task["correct"], str):
                # Пробуем преобразовать "a", "A", "1" в индекс
                opt_map = {"a": 0, "A": 0, "1": 0, "b": 1, "B": 1, "2": 1, 
                          "c": 2, "C": 2, "3": 2, "d": 3, "D": 3, "4": 3}
                task["correct"] = opt_map.get(task["correct"].lower(), 0)
        
        # Для открытых вопросов
        if task.get("type") == "open" or "options" not in task or not task["options"]:
            task["options"] = None
            if "correct" not in task:
                task["correct"] = "Ответ не указан"
        
        # Default значения
        task.setdefault("time_limit_sec", 30)
        task.setdefault("adaptive_level", 2)
        task.setdefault("type", "test")
        
        # Ограничиваем adaptive_level 1-3
        if task["adaptive_level"] < 1:
            task["adaptive_level"] = 1
        if task["adaptive_level"] > 3:
            task["adaptive_level"] = 3
        
        validated.append(task)
    
    return validated


def sanitize_latex(obj: Any) -> Any:
    """Заменяет LaTeX на читаемый текст."""
    if isinstance(obj, dict):
        return {k: sanitize_latex(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_latex(i) for i in obj]
    if isinstance(obj, str):
        # Убираем доллары
        obj = re.sub(r'\$([^$]+)\$', r'\1', obj)
        # \frac{a}{b} → a/b
        obj = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', r'\1/\2', obj)
        # \times → ×
        obj = obj.replace(r'\times', '×')
        # \div → ÷
        obj = obj.replace(r'\div', '÷')
        # \sqrt{x} → √(x)
        obj = re.sub(r'\\sqrt\{([^}]+)\}', r'√(\1)', obj)
        # Убираем другие LaTeX-команды
        obj = re.sub(r'\\(?:frac|times|div|sqrt|cdot|pm|mp)\b', '', obj)
        # Очищаем лишние скобки
        obj = re.sub(r'\{\}', '', obj)
        return obj.strip()
    return obj


JSON_ONLY_SUFFIX = """
\n\n⚠️ ВЕРНИ ТОЛЬКО JSON. Без пояснений. Без markdown. Начинай с { и заканчивай }.
Пример правильного ответа:
{"tasks": [{"text": "вопрос", "options": ["a","b","c","d"], "correct": 0}]}
"""