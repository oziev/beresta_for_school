"""Eight GigaChat prompt templates from ТЗ §8 (Python f-strings / builders)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.schemas import GenerationParams, Task

if TYPE_CHECKING:
    from app.schemas import PedagogicalFeatures  # noqa: F401


def _types_str(types: list[str]) -> str:
    return ", ".join(types)


def _game_block(params: GenerationParams) -> str:
    if not params.game_mode:
        return ""
    theme = params.game_theme or "квест"
    return f"\nВключён игровой режим: оберни задания в короткий сюжет ({theme}), без потери учебной ценности.\n"


def _profile_block(profile: dict[str, Any] | None) -> str:
    if not profile:
        return ""
    return f"""
Учитывай стиль учителя из профиля:
- Предпочитаемая сложность: {profile.get("preferred_difficulty", "medium")}
- Любимые типы: {_types_str(profile.get("preferred_task_types", []))}
- Стиль языка: {profile.get("language_style", "friendly")}
- ТЕМЫ-ТАБУ (НЕ использовать): {", ".join(profile.get("hates_topics", []))}
- Типичное время на задание: {profile.get("avg_time_per_task", 45)} секунд
- Стиль подсказок: {profile.get("hint_style", "step_by_step")}
"""


def _pedagogical_block(params: GenerationParams) -> str:
    p = params.pedagogical
    blocks: list[str] = []
    if p.sources.enabled:
        if p.sources.mode == "my":
            names = ", ".join(src.get("name", "") for src in p.sources.my_sources if src.get("name"))
            blocks.append(
                f"""
Добавь к каждому заданию ссылку на источник в формате [Источник: название].
Используй ТОЛЬКО источники из списка: {names or "список пуст"}.
"""
            )
        else:
            blocks.append(
                """
Добавь к каждому заданию ссылку на источник в формате [Источник: название].
Подбирай реалистичные источники: учебник, ВПР, ФГОС или авторская разработка.
"""
            )
    if p.mistakes.enabled:
        blocks.append(
            f"""
Сгенерируй блок typical_mistakes из {p.mistakes.count} типичных ошибок по теме.
Для каждой ошибки укажи mistake, correct, why_happens.
{"Добавь lifehack для каждой ошибки." if p.mistakes.add_lifehacks else ""}
{"Добавь common_trap для ловушек, где чаще ошибаются." if p.mistakes.add_common_traps else ""}
"""
        )
    if p.timing.enabled:
        blocks.append(
            f"""
Сгенерируй timeline для урока длительностью {p.timing.lesson_duration} минут.
Укажи этап, минуты и номера заданий.
{"Добавь extra_tasks, если осталось время." if p.timing.add_extra_tasks else ""}
"""
        )
    if p.scaffolding.enabled:
        blocks.append(
            f"""
Для заданий уровня {p.scaffolding.min_level} и выше добавь scaffolding_steps.
Стиль подсказок: {p.scaffolding.style}.
"""
        )
    if p.emotional.enabled:
        blocks.append(
            f"""
Сгенерируй reflection для эмоциональной рефлексии.
Тип рефлексии: {p.emotional.type}.
{"Добавь creative_task." if p.emotional.add_creative else ""}
"""
        )
    return "\n".join(blocks)


def prompt_generate_sheet(
    *,
    topic: str,
    grade: int,
    subject: str,
    params: GenerationParams,
    teacher_profile: dict[str, Any] | None = None,
) -> str:
    """Промпт №1: полная генерация листа."""
    p = params
    return f"""Ты — опытный педагог по {subject}, {grade} класс.

Сгенерируй {p.task_count} заданий по теме "{topic}" с параметрами:
- Типы заданий: {_types_str(p.task_types)} (например, тест, открытый вопрос, задача, творческое)
- Распределение сложности: {p.difficulty_distribution} (равномерно/больше базовых/больше сложных)
- Формат ответа: {p.answer_format} (тест/открытый текст/смешанный)
- Время на диагностику (контекст урока): {p.diagnostic_time_sec} сек
{_game_block(p)}
{_profile_block(teacher_profile)}
{_pedagogical_block(p)}

Верни строго JSON:
{{
  "tasks": [
    {{
      "text": "текст задания",
      "options": ["вариант1", "вариант2", "вариант3", "вариант4"],
      "correct": 0,
      "time_limit_sec": 30,
      "adaptive_level": 1,
      "type": "test"
    }}
  ],
  "sources": [],
  "typical_mistakes": [],
  "timeline": [],
  "reflection": null
}}

Правила качества:
- Верни РОВНО {p.task_count} объектов в массиве tasks.
- Для теста: 4 варианта, дистракторы правдоподобны; options — массив из 4 строк, correct — индекс 0..3.
- Для открытого вопроса: options = null, correct — краткая строка-эталон для проверки.
- Поле type одно из: test, open, problem, creative, graph.
- adaptive_level: целое 1..3 (1=база, 3=сложный).
- НЕ используй темы-табу из профиля (если указаны).
"""


def prompt_diagnostic(*, topic: str, grade: int) -> str:
    """Промпт №2: три диагностических вопроса."""
    return f"""Сгенерируй 3 быстрых вопроса по теме "{topic}" для {grade} класса.
Вопросы должны проверять:
1. Знание определения/формулы (10 сек)
2. Базовое применение (15 сек)
3. Логику/нестандартную ситуацию (20 сек)

Верни JSON:
{{
  "diagnostic": [
    {{"text": "вопрос 1", "options": ["a","b","c","d"], "correct": 0, "time_sec": 10}}
  ]
}}
"""


def prompt_dashboard_advice(*, topic: str, grade: int, statistics: str) -> str:
    """Промпт №3: совет учителю по статистике."""
    return f"""Проанализируй статистику класса по теме "{topic}" ({grade} класс):
{statistics}

Верни JSON с советом учителю (до 200 символов):
{{
  "advice": "конкретная рекомендация, что повторить и как объяснить"
}}
"""


def prompt_methodological_reflection(*, topic: str, grade: int) -> str:
    """Промпт №4: методическая рефлексия."""
    return f"""Ты — заслуженный методист. Проанализируй задания по теме "{topic}" для {grade} класса.

Верни JSON:
{{
  "strengths": "сильные стороны (до 200 символов)",
  "pitfalls": "потенциальные ошибки (до 200 символов)",
  "next_lesson": "идеи для следующего занятия (до 200 символов)",
  "time_estimate": "ожидаемое время: слабые/средние/сильные (до 100 символов)"
}}
"""


def prompt_train_teacher_twin(
    *,
    count: int,
    samples: str,
    deleted_creative: int,
    avg_time: int,
    frequent_type: str,
    frequent_topic: str,
) -> str:
    """Промпт №5: обучение виртуального двойника."""
    return f"""Ты — аналитик образовательного контента. Проанализируй {count} правок учителя:

Примеры правок:
{samples}

Статистика:
- Удалено заданий типа "творческое": {deleted_creative}
- Чаще всего менял время на {avg_time} сек
- Добавлял {frequent_type} чаще всего
- Тема, которую правил чаще всего: {frequent_topic}

Верни JSON профиля:
{{
  "preferred_difficulty": "basic/medium/advanced",
  "preferred_task_types": ["test", "problem"],
  "avg_time_per_task": 45,
  "language_style": "formal/casual/friendly",
  "hates_topics": ["тема1", "тема2"],
  "loves_visuals": true,
  "hint_style": "step_by_step/no_spoiler/example_first"
}}
"""


def prompt_regenerate_task(*, original_task: Task, topic: str, grade: int, feedback: str | None) -> str:
    """Промпт №6: альтернативный вариант задания."""
    fb = feedback or "без дополнительных пожеланий"
    return f"""Ты — педагог. Сгенерируй альтернативный вариант задания того же уровня сложности.

Оригинал: {original_task.model_dump_json()}
Уровень: {original_task.adaptive_level}
Тема: {topic}
Класс: {grade}
Пожелания учителя: {fb}

Верни JSON ОДНОГО задания (как элемент массива tasks):
{{"text": "...", "options": [...], "correct": 0, "time_limit_sec": 30, "adaptive_level": {original_task.adaptive_level}, "type": "{original_task.type}"}}
"""


def prompt_hint(*, task_text: str, mistake_hint: str) -> str:
    """Промпт №7: короткая подсказка при ошибке."""
    return f"""Ученик ошибся в задании: "{task_text}"
Тип ошибки: {mistake_hint}
Дай короткую подсказку (1 предложение, до 100 символов), без спойлера ответа.
Верни JSON: {{"hint": "..."}}
"""


def prompt_student_final_advice(
    *,
    topic: str,
    correct_count: int,
    total_count: int,
    initial_level: int,
    final_level: int,
) -> str:
    """Промпт №8: финальный совет ученику."""
    return f"""Ученик решил {correct_count} из {total_count} заданий по теме "{topic}".
Начальный уровень: {initial_level}, финальный: {final_level}.
Дай короткий персонализированный совет (1 предложение), что повторить.
Верни JSON: {{"advice": "..."}}
"""


def prompt_hot_mistakes(*, topic: str, grade: int, subject: str, count: int = 10) -> str:
    """Промпт №11: «Горячая десятка» — список типичных ошибок по теме."""
    return f"""Ты — методист по {subject} ({grade} класс). Составь горячую десятку
типичных ошибок учеников по теме "{topic}".

Верни JSON:
{{
  "mistakes": [
    {{"mistake": "что делают не так",
      "correct": "как правильно",
      "why_happens": "почему так ошибаются",
      "lifehack": "короткий лайфхак для запоминания"}}
  ]
}}

Правила:
- Ровно {count} ошибок.
- Формулируй кратко и конкретно (1 предложение на поле).
- Без воды и без воспитательных эпитетов.
"""


def prompt_example_with_mistakes(*, title: str, content: str, grade: int) -> str:
    """Промпт №12: пример с типичными ошибками для конкретной раздатки."""
    return f"""Ты — учитель, объясняющий типичные ошибки.

Раздатка: "{title}"
Содержание: {content[:1500]}
Класс: {grade}

Сгенерируй 2-3 примера НЕПРАВИЛЬНЫХ решений с разбором.

Верни JSON:
{{
  "example_mistakes": [
    {{"wrong_answer": "типичный неправильный ответ ученика",
      "why_wrong": "почему это ошибка",
      "correct_answer": "правильный ответ",
      "teacher_comment": "что сказать классу"}}
  ]
}}
"""


def prompt_parse_lesson_plan(*, text: str) -> str:
    return f"""Ты — ассистент учителя. Проанализируй загруженный план урока:

{text}

Извлеки структуру в JSON:
{{
  "stages": [
    {{
      "name": "название этапа",
      "goal": "цель этапа",
      "time_minutes": 10,
      "activity_type": "quiz/explanation/practice/reflection/homework",
      "needs_handout": true,
      "recommended_handout_type": "worksheet/memo/reflection/table/schema"
    }}
  ]
}}
"""


def _kit_pedagogical_block(params: "PedagogicalFeatures | None") -> str:
    if params is None:
        return ""
    blocks: list[str] = []
    if params.sources.enabled:
        if params.sources.mode == "my":
            names = ", ".join(src.get("name", "") for src in params.sources.my_sources if src.get("name"))
            blocks.append(
                f"К каждой раздатке добавь поле sources — массив с одним объектом "
                f'{{"name": "..."}}, используй ТОЛЬКО эти источники: {names or "(пусто)"}.'
            )
        else:
            blocks.append(
                "К каждой раздатке добавь поле sources — массив 1–2 реалистичных источника "
                "(учебник, ВПР, ФГОС, авторская разработка) в формате [{\"name\": \"...\"}]."
            )
    if params.mistakes.enabled:
        blocks.append(
            f"Сгенерируй блок typical_mistakes (горячая десятка) — массив из "
            f"{params.mistakes.count} типичных ошибок по теме с полями mistake, correct, why_happens"
            + (", lifehack" if params.mistakes.add_lifehacks else "")
            + (", common_trap" if params.mistakes.add_common_traps else "")
            + "."
        )
    if params.timing.enabled:
        blocks.append(
            f"Сгенерируй timeline для урока длительностью {params.timing.lesson_duration} минут — "
            "массив объектов {stage, minutes, item_indices}."
            + (" Добавь extra_tasks с запасными заданиями." if params.timing.add_extra_tasks else "")
        )
    if params.scaffolding.enabled:
        blocks.append(
            f"Для каждой раздатки уровня сложности {params.scaffolding.min_level} и выше "
            f"добавь scaffolding_steps — массив пошаговых подсказок (стиль: {params.scaffolding.style})."
        )
    if params.emotional.enabled:
        blocks.append(
            f"В блок reflection положи объект для эмоциональной рефлексии типа {params.emotional.type} "
            "с полями question, options."
            + (" Добавь creative_task — короткое творческое задание." if params.emotional.add_creative else "")
        )
    return ("\n".join("- " + b for b in blocks) + "\n") if blocks else ""


def _kit_profile_block(profile: dict[str, Any] | None) -> str:
    if not profile:
        return ""
    return f"""
Учитывай стиль учителя:
- Сложность: {profile.get("preferred_difficulty", "medium")}
- Любимые типы: {", ".join(profile.get("preferred_task_types", []))}
- Стиль: {profile.get("language_style", "friendly")}
- ТЕМЫ-ТАБУ (исключи): {", ".join(profile.get("hates_topics", []))}
- Подсказки: {profile.get("hint_style", "step_by_step")}
"""


def prompt_generate_kit_from_plan(
    *,
    lesson_plan: str,
    topic: str | None,
    grade: int,
    subject: str,
    lesson_type: str | None = None,
    global_complexity: int = 2,
    pedagogical: Any | None = None,
    teacher_profile: dict[str, Any] | None = None,
) -> str:
    complexity_names = {1: "базовый (для слабых)", 2: "средний", 3: "продвинутый (для сильных)"}
    return f"""Ты — эксперт по разработке учебных материалов по ФГОС.

План урока (JSON): {lesson_plan}
Тема: {topic or "определи по плану"}
Класс: {grade}
Предмет: {subject}
Тип урока: {lesson_type or "комбинированный"}
Глобальная сложность: {complexity_names.get(global_complexity, "средний")}

{_kit_profile_block(teacher_profile)}

Для каждого этапа, где needs_handout = true, сгенерируй ОДНУ раздатку.
Тип раздатки бери из recommended_handout_type этапа.

Верни строго валидный JSON:
{{
  "items": [
    {{
      "stage_name": "Актуализация знаний",
      "type": "cards",
      "title": "Карточки для разминки",
      "content_levels": {{
        "basic": "текст для слабых учеников",
        "medium": "текст для средних учеников",
        "advanced": "текст для сильных учеников"
      }},
      "complexity_level": 2,
      "teacher_notes": "методические заметки (1-2 предложения)",
      "answer_key": {{"basic": "ответ", "medium": "ответ", "advanced": "ответ"}},
      "scaffolding_steps": [],
      "sources": [],
      "example_mistakes": []
    }}
  ],
  "typical_mistakes": [],
  "timeline": [],
  "reflection": null
}}

Правила:
- Сгенерируй 3-6 раздаток (по числу этапов с needs_handout=true).
- Поле type СТРОГО одно из: cards, worksheet, memo, reflection, table, schema, homework.
- content_levels.basic / medium / advanced — РАЗНЫЕ по сложности тексты, не дублируй.
- Базовая сложность глобально равна {global_complexity}: для basic снижай на 1, для advanced повышай на 1.
- answer_key для каждого уровня — короткий эталонный ответ или критерий.
- teacher_notes — конкретные подсказки учителю (тайминг, акценты, типичные затыки).
- Если в плане есть домашнее задание — используй type=homework на этом этапе.

Особые требования (педагогические фишки):
{_kit_pedagogical_block(pedagogical)}
"""
