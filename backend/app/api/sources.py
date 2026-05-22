from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import TeacherSource, User
from app.schemas import TeacherSourceCreate, TeacherSourceRead

router = APIRouter(tags=["sources"])
DEMO_EMAIL = "demo@beresta.local"


async def ensure_demo_user(db: AsyncSession) -> None:
    res = await db.execute(select(User).where(User.email == DEMO_EMAIL))
    if res.scalar_one_or_none() is None:
        db.add(User(email=DEMO_EMAIL, password_hash=None, demo_id="demo"))
        await db.flush()


@router.get("/sources", response_model=list[TeacherSourceRead])
async def list_sources(db: Annotated[AsyncSession, Depends(get_session)]) -> list[TeacherSourceRead]:
    res = await db.execute(
        select(TeacherSource)
        .where(TeacherSource.user_email == DEMO_EMAIL)
        .order_by(TeacherSource.created_at.desc())
    )
    return [TeacherSourceRead.model_validate(item, from_attributes=True) for item in res.scalars().all()]


@router.post("/sources", response_model=TeacherSourceRead)
async def create_source(
    body: TeacherSourceCreate,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> TeacherSourceRead:
    await ensure_demo_user(db)
    source = TeacherSource(
        user_email=DEMO_EMAIL,
        name=body.name.strip(),
        category=body.category.strip() if body.category else None,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return TeacherSourceRead.model_validate(source, from_attributes=True)


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(
    source_id: UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    res = await db.execute(
        select(TeacherSource).where(
            TeacherSource.id == source_id,
            TeacherSource.user_email == DEMO_EMAIL,
        )
    )
    source = res.scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="source_not_found")
    await db.delete(source)
    await db.commit()
    return Response(status_code=204)
