"""POST /templates/save, GET /templates/my (FR-20..22)."""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas import TemplateListItem, TemplateSaveRequest
from app.teacher.templates import DEMO_EMAIL, delete_template, list_templates, save_template

log = logging.getLogger(__name__)
router = APIRouter(tags=["templates"])


@router.post("/templates/save")
async def templates_save(
    body: TemplateSaveRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    tpl = await save_template(db, body.name, body.params.model_dump(mode="json"))
    return {"template_id": str(tpl.id), "name": tpl.name}


@router.get("/templates/my", response_model=list[TemplateListItem])
async def templates_my(
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[TemplateListItem]:
    tpls = await list_templates(db)
    return [TemplateListItem(id=t.id, name=t.name) for t in tpls]


@router.delete("/templates/{template_id}")
async def templates_delete(
    template_id: str,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    import uuid
    try:
        tid = uuid.UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_uuid")
    ok = await delete_template(db, tid)
    if not ok:
        raise HTTPException(status_code=404, detail="template_not_found")
    return {"success": True}
