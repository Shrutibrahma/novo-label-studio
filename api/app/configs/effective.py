"""Effective label config for a part and a label type: the part's current override for that type, else the
type's current default (D11, with saved label types from migration 0003)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.models import LabelConfig, LabelType


async def resolve_type(db: AsyncSession, type_id: uuid.UUID | None = None) -> LabelType:
    """The given (active) label type, or the first one when none is given."""
    if type_id is not None:
        t = await db.get(LabelType, type_id)
        if t is None or t.archived:
            raise ApiError("NOT_FOUND")
        return t
    t = (await db.execute(select(LabelType).where(LabelType.archived.is_(False))
                          .order_by(LabelType.sort_order, LabelType.created_at).limit(1))).scalar_one_or_none()
    if t is None:
        raise ApiError("NOT_FOUND")
    return t


async def current_default(db: AsyncSession, type_id: uuid.UUID | None = None) -> LabelConfig:
    t = await resolve_type(db, type_id)
    cfg = (await db.execute(select(LabelConfig).where(LabelConfig.label_type_id == t.id, LabelConfig.scope == "default",
                                                      LabelConfig.is_current.is_(True)))).scalar_one_or_none()
    if cfg is None:
        raise ApiError("NOT_FOUND")
    return cfg


async def current_override(db: AsyncSession, part_id: uuid.UUID, type_id: uuid.UUID | None = None
                           ) -> LabelConfig | None:
    t = await resolve_type(db, type_id)
    return (await db.execute(select(LabelConfig).where(LabelConfig.label_type_id == t.id, LabelConfig.scope == "part",
                                                       LabelConfig.part_id == part_id,
                                                       LabelConfig.is_current.is_(True)))).scalar_one_or_none()


async def effective_config(db: AsyncSession, part_id: uuid.UUID, type_id: uuid.UUID | None = None) -> LabelConfig:
    return await current_override(db, part_id, type_id) or await current_default(db, type_id)
