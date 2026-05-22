"""FastAPI application entrypoint — связное SSR-приложение."""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.adapt import router as adapt_router
from app.api.dashboard import router as dashboard_router
from app.api.extra import router as extra_router
from app.api.generate import router as generate_router
from app.api.kits import router as kits_router
from app.api.materials import router as materials_router
from app.api.materials import task_router as materials_task_router
from app.api.profile import router as profile_router
from app.api.sources import router as sources_router
from app.api.templates import router as templates_router
from app.config import get_settings
from app.database import get_session
from app.llm.client import GigaChatClient
from app.models import Kit, Material, UserTemplate
from app.schemas import Task

logging.basicConfig(level=logging.ERROR)
log = logging.getLogger(__name__)

settings = get_settings()
templates = Jinja2Templates(directory="templates")

LEVEL_NAMES = {1: "Базовый", 2: "Средний", 3: "Сложный"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    try:
        client = aioredis.from_url(s.redis_url, decode_responses=True)
        await client.ping()
        app.state.redis = client
    except Exception as exc:
        log.error("Redis init failed: %s", exc)
        app.state.redis = None
    app.state.llm = GigaChatClient(s)
    yield
    await app.state.llm.aclose()
    r = getattr(app.state, "redis", None)
    if r is not None:
        await r.aclose()


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# API routers (логика не меняется)
app.include_router(generate_router)
app.include_router(materials_task_router)
app.include_router(materials_router)
app.include_router(adapt_router)
app.include_router(dashboard_router)
app.include_router(templates_router)
app.include_router(profile_router)
app.include_router(extra_router)
app.include_router(kits_router)
app.include_router(sources_router)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/ping")
async def ping() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
async def health_db(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"db": "ok"}


# ── Landing & teacher flow ────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def landing_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="landing.html", context={})


@app.get("/teacher/select-template")
async def teacher_select_template_redirect() -> RedirectResponse:
    return RedirectResponse(url="/teacher/create", status_code=301)


@app.get("/teacher/create", response_class=HTMLResponse)
async def teacher_create(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="teacher/create.html", context={})


@app.get("/teacher/create/lesson-type", response_class=HTMLResponse)
async def teacher_create_lesson_type(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="teacher/create.html", context={})


@app.get("/teacher/create/plan", response_class=HTMLResponse)
async def teacher_create_plan(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="teacher/create_plan.html", context={})


@app.get("/teacher/create/scratch", response_class=HTMLResponse)
async def teacher_create_scratch(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="teacher/create_scratch.html", context={})


@app.get("/teacher/configure-stages", response_class=HTMLResponse)
async def teacher_configure_stages(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="teacher/configure_stages.html", context={})


@app.get("/teacher/generate", response_class=HTMLResponse)
async def teacher_generate_legacy(request: Request) -> HTMLResponse:
    """Старый поток (один рабочий лист). Оставлен как fallback."""
    return templates.TemplateResponse(request=request, name="teacher/generate.html", context={})


@app.get("/teacher/materials", response_class=HTMLResponse)
async def teacher_materials(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    res = await session.execute(select(Material).order_by(Material.created_at.desc()).limit(50))
    materials = list(res.scalars().all())
    return templates.TemplateResponse(
        request=request,
        name="teacher/materials.html",
        context={"materials": materials},
    )


@app.get("/teacher/kits", response_class=HTMLResponse)
async def teacher_kits_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    from sqlalchemy.orm import selectinload

    res = await session.execute(select(Kit).options(selectinload(Kit.items)).order_by(Kit.created_at.desc()).limit(100))
    kits = list(res.scalars().all())
    return templates.TemplateResponse(
        request=request,
        name="teacher/kits.html",
        context={"kits": kits},
    )


@app.get("/teacher/profile", response_class=HTMLResponse)
async def teacher_profile_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="teacher/profile.html", context={})


@app.get("/teacher/templates", response_class=HTMLResponse)
async def teacher_templates_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    from sqlalchemy.orm import selectinload

    tres = await session.execute(
        select(Kit)
        .options(selectinload(Kit.items))
        .where(Kit.is_template.is_(True))
        .order_by(Kit.created_at.desc())
        .limit(100)
    )
    template_kits = list(tres.scalars().all())
    lres = await session.execute(select(UserTemplate).order_by(UserTemplate.created_at.desc()).limit(50))
    templates_legacy = list(lres.scalars().all())
    return templates.TemplateResponse(
        request=request,
        name="teacher/templates.html",
        context={"templates": template_kits, "templates_legacy": templates_legacy},
    )


@app.get("/teacher/sources", response_class=HTMLResponse)
async def teacher_sources_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="teacher/sources.html", context={})


@app.get("/teacher/adapt/kit/{kit_id}", response_class=HTMLResponse)
async def teacher_adapt_kit_page(
    request: Request,
    kit_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """QR-страница учителя для комплекта (адаптив по элементам комплекта)."""
    import base64
    import io as _io

    import qrcode

    from sqlalchemy.orm import selectinload

    res = await session.execute(select(Kit).options(selectinload(Kit.items)).where(Kit.id == kit_id))
    kit = res.scalar_one_or_none()
    if kit is None:
        raise HTTPException(status_code=404, detail="kit_not_found")
    base_url = str(request.base_url).rstrip("/")
    student_url = f"{base_url}/student/adapt/{kit_id}"
    qr_img = qrcode.make(student_url)
    buf = _io.BytesIO()
    qr_img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()
    return templates.TemplateResponse(
        request=request,
        name="teacher/adapt_kit.html",
        context={
            "kit": kit,
            "qr_b64": qr_b64,
            "qr_url": student_url,
            "student_url": student_url,
        },
    )


@app.get("/teacher/editor/{material_id}", response_class=HTMLResponse)
async def teacher_editor(
    request: Request,
    material_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    res = await session.execute(select(Material).where(Material.id == material_id))
    material = res.scalar_one_or_none()
    if material is None:
        raise HTTPException(status_code=404, detail="material_not_found")
    tasks = [Task.model_validate(t) for t in material.tasks]
    return templates.TemplateResponse(
        request=request,
        name="teacher/editor.html",
        context={"material": material, "tasks": tasks},
    )


@app.get("/teacher/kits/{kit_id}", response_class=HTMLResponse)
async def teacher_kit_editor(
    request: Request,
    kit_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    from sqlalchemy.orm import selectinload

    res = await session.execute(select(Kit).options(selectinload(Kit.items)).where(Kit.id == kit_id))
    kit = res.scalar_one_or_none()
    if kit is None:
        raise HTTPException(status_code=404, detail="kit_not_found")
    return templates.TemplateResponse(
        request=request,
        name="teacher/kit_editor.html",
        context={"kit": kit, "items": list(kit.items)},
    )


@app.get("/teacher/kits/{kit_id}/variants", response_class=HTMLResponse)
async def teacher_kit_variants(
    request: Request,
    kit_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    from sqlalchemy.orm import selectinload

    res = await session.execute(select(Kit).options(selectinload(Kit.items)).where(Kit.id == kit_id))
    kit = res.scalar_one_or_none()
    if kit is None:
        raise HTTPException(status_code=404, detail="kit_not_found")
    return templates.TemplateResponse(
        request=request,
        name="teacher/kit_variants.html",
        context={"kit": kit},
    )


@app.get("/teacher/dashboard/{material_id}", response_class=HTMLResponse)
async def teacher_dashboard_page(
    request: Request,
    material_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    from app.dashboard.advice import get_advice
    from app.dashboard.aggregator import aggregate, aggregate_kit

    stats = await aggregate(material_id, session)
    if not stats:
        stats = await aggregate_kit(material_id, session)
    if not stats:
        raise HTTPException(status_code=404, detail="material_or_kit_not_found")
    advice = await get_advice(stats, request.app.state.llm, getattr(request.app.state, "redis", None))
    return templates.TemplateResponse(
        request=request,
        name="teacher/dashboard.html",
        context={"stats": stats, "advice": advice, "material_id": material_id},
    )


# ── Student result (данные из Redis-сессии) ───────────────────────────────────

@app.get("/student/result/{session_id}", response_class=HTMLResponse)
async def student_result_page(request: Request, session_id: UUID) -> HTMLResponse:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(status_code=503, detail="redis_unavailable")
    raw = await redis.get(f"adapt:session:{session_id}")
    if not raw:
        raise HTTPException(status_code=404, detail="session_not_found")
    sess = json.loads(raw)
    answered = sess.get("answered") or []
    correct_count = sum(1 for a in answered if a.get("correct"))
    total_count = len(answered)
    final_level = sess.get("final_level") or sess.get("current_level") or 2
    initial_level = sess.get("initial_level") or 2
    return templates.TemplateResponse(
        request=request,
        name="student/result.html",
        context={
            "correct_count": correct_count,
            "total_count": total_count,
            "final_level": final_level,
            "initial_level": initial_level,
            "level_name": LEVEL_NAMES.get(final_level, "Средний"),
            "topic": sess.get("topic", ""),
            "advice": sess.get("final_advice", ""),
        },
    )


# ── Редиректы со старых URL ───────────────────────────────────────────────────

@app.get("/editor/{material_id}")
async def redirect_editor(material_id: UUID) -> RedirectResponse:
    return RedirectResponse(url=f"/teacher/editor/{material_id}", status_code=301)


@app.get("/twin")
async def redirect_twin() -> RedirectResponse:
    return RedirectResponse(url="/teacher/profile", status_code=301)


@app.get("/dashboard/{material_id}")
async def redirect_dashboard(material_id: UUID) -> RedirectResponse:
    return RedirectResponse(url=f"/teacher/dashboard/{material_id}", status_code=301)
