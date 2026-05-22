# Береста

Веб-сервис для учителей: комплекты раздаточных материалов, привязанные к этапам урока по ФГОС, с педагогическими фишками и адаптивным режимом ученика.

Стек: **FastAPI · SQLAlchemy async · PostgreSQL 15 · Redis 7 · GigaChat · WeasyPrint · python-docx · Jinja2 + Alpine.js + HTMX + Tailwind**.

## Быстрый старт

```bash
git clone <repo>
cd beresta

cp .env.example .env
# Заполните GIGACHAT_CLIENT_ID / GIGACHAT_CLIENT_SECRET
# или поставьте BERESTA_LLM_STUB=true для офлайн-демо

docker compose up -d --build
curl http://localhost:8000/ping     # → {"status":"ok"}
```

Открыть в браузере: **http://localhost:8000**.

### Без ключей GigaChat (stub-режим)

```dotenv
BERESTA_LLM_STUB=true
```

## Основные сценарии и страницы (на доработке)

| Сценарий | Маршрут |
|---|---|
| Лендинг (выбор роли) | `/` |
| Учитель — выбор режима и типа урока | `/teacher/create` |
| Конструктор этапов (с нуля по ФГОС) | `/teacher/configure-stages` |
| Загрузка плана урока (TXT/PDF/DOCX) | `/teacher/create/plan` |
| Экспресс-режим (тема + сложность) | `/teacher/create/scratch` |
| Мои комплекты | `/teacher/kits` |
| Редактор комплекта | `/teacher/kits/{id}` |
| 3 разноуровневых варианта | `/teacher/kits/{id}/variants` |
| QR для класса (kit) | `/teacher/adapt/kit/{id}` |
| Дашборд + форк после урока | `/teacher/dashboard/{id}` |
| Шаблоны | `/teacher/templates` |
| Источники | `/teacher/sources` |
| Виртуальный двойник | `/teacher/profile` |
| Адаптив ученика | `/student/adapt/{material_or_kit_id}` |
| Результат ученика | `/student/result/{session_id}` |

## Ключевые API (на доработке)

- `GET /lesson-types` — каталог типов уроков с этапами по ФГОС.
- `POST /upload-lesson-plan` — парсинг файла плана (TXT/PDF/DOCX).
- `POST /generate-from-plan` — основная генерация комплекта.
- `POST /generate-from-scratch` — экспресс-генерация без плана.
- `GET/POST/PUT/DELETE /kits` и `/kit-items` — CRUD комплектов.
- `POST /kits/{id}/variants` — три разноуровневых копии (US-06).
- `POST /kits/{id}/fork` — форк на основе оценок урока (US-10).
- `POST /kits/{id}/ungeneratable` — рукописный (негенерабельный) элемент.
- `POST /kits/{id}/hot-mistakes` — «Горячая десятка» ошибок (US-12).
- `POST /kit-items/{id}/generate-example` — пример с ошибками (US-16).
- `PUT /kits/{id}/reorder` — drag-and-drop порядка раздаток.
- `POST /export/kit/{id}/{pdf|docx|zip}` — экспорт (PDF с layout 4-карточки/флипчарт/A3, DOCX с таблицами, ZIP с папками по этапам).
- `GET/PUT /design-settings` — оформление (шрифт, поля, служебные поля).
- `GET/POST/DELETE /sources` — библиотека источников.
- `GET/POST /profile`, `POST /profile/train`, `POST /profile/reset` — виртуальный двойник учителя.
- `GET /reflection/{id}` — методическая рефлексия (промпт №4).

