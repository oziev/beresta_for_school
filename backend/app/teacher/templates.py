"""CRUD for user_templates table."""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserTemplate

log = logging.getLogger(__name__)

DEMO_EMAIL = "demo@beresta.local"


async def save_template(
    db: AsyncSession,
    name: str,
    params: dict[str, Any],
    user_email: str = DEMO_EMAIL,
) -> UserTemplate:
    tpl = UserTemplate(
        id=uuid.uuid4(),
        user_email=user_email,
        name=name,
        params=params,
    )
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl)
    return tpl


async def list_templates(
    db: AsyncSession,
    user_email: str = DEMO_EMAIL,
) -> list[UserTemplate]:
    res = await db.execute(
        select(UserTemplate)
        .where(UserTemplate.user_email == user_email)
        .order_by(UserTemplate.created_at.desc())
    )
    return list(res.scalars().all())


async def delete_template(
    db: AsyncSession,
    template_id: uuid.UUID,
    user_email: str = DEMO_EMAIL,
) -> bool:
    res = await db.execute(
        select(UserTemplate).where(
            UserTemplate.id == template_id,
            UserTemplate.user_email == user_email,
        )
    )
    tpl = res.scalar_one_or_none()
    if not tpl:
        return False
    await db.delete(tpl)
    await db.commit()
    return True
