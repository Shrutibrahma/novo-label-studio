"""Effective label config for a part: its current per-part override, else the current default (D11)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.models import LabelConfig


async def current_default(db: AsyncSession) -> LabelConfig:
    cfg = (await db.execute(select(LabelConfig).where(LabelConfig.scope == "default",
                                                      LabelConfig.is_current.is_(True)))).scalar_one_or_none()
    if cfg is None:
        raise ApiError("NOT_FOUND")
    return cfg


async def current_override(db: AsyncSession, part_id: uuid.UUID) -> LabelConfig | None:
    return (await db.execute(select(LabelConfig).where(LabelConfig.scope == "part", LabelConfig.part_id == part_id,
                                                       LabelConfig.is_current.is_(True)))).scalar_one_or_none()


async def effective_config(db: AsyncSession, part_id: uuid.UUID) -> LabelConfig:
    return await current_override(db, part_id) or await current_default(db)
