"""Saved label types (migration 0003): Label, Bin, Rack, Workstation, Kanban, ... each with its own versioned
default design and per-part overrides. Printing picks a type."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.audit import audit
from app.auth.deps import DB, Admin, AnyUser
from app.configs.effective import current_default, resolve_type
from app.errors import ApiError
from app.models import LabelConfig, LabelType
from app.parts.router import SizeBrief, size_brief

router = APIRouter(tags=["label types"])

MAX_TYPES = 30


class LabelTypeOut(BaseModel):
    id: str
    name: str
    sort_order: int
    size: SizeBrief
    layout: str
    version: int
    default_config_id: str
    override_count: int
    created_at: datetime


class TypeIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    copy_from_type_id: uuid.UUID | None = None


class TypePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    sort_order: int | None = Field(default=None, ge=0, le=1000)


async def type_out(db: DB, t: LabelType) -> LabelTypeOut:
    cfg = await current_default(db, t.id)
    overrides = (await db.execute(select(func.count()).select_from(LabelConfig).where(
        LabelConfig.label_type_id == t.id, LabelConfig.scope == "part", LabelConfig.is_current.is_(True)))).scalar_one()
    return LabelTypeOut(id=str(t.id), name=t.name, sort_order=t.sort_order, size=await size_brief(db, cfg.label_size_id),
                        layout=str(cfg.spec.get("style", {}).get("layout", "lines")), version=cfg.version,
                        default_config_id=str(cfg.id), override_count=int(overrides), created_at=t.created_at)


async def name_free(db: DB, name: str, except_id: uuid.UUID | None = None) -> None:
    q = select(LabelType.id).where(LabelType.archived.is_(False), func.lower(func.btrim(LabelType.name)) == name.lower())
    if except_id is not None:
        q = q.where(LabelType.id != except_id)
    if (await db.execute(q)).first() is not None:
        raise ApiError("LABEL_TYPE_EXISTS", fields={"name": "A label type with this name already exists."})


@router.get("/label-types", response_model=list[LabelTypeOut])
async def list_types(_: AnyUser, db: DB) -> list[LabelTypeOut]:
    types = (await db.execute(select(LabelType).where(LabelType.archived.is_(False))
                              .order_by(LabelType.sort_order, LabelType.created_at))).scalars().all()
    return [await type_out(db, t) for t in types]


@router.post("/label-types", response_model=LabelTypeOut, status_code=201)
async def create_type(body: TypeIn, user: Admin, db: DB) -> LabelTypeOut:
    """A new type starts as a copy of another type's current default design (the first type when not given)."""
    name = body.name.strip()
    if not name:
        raise ApiError("FIELD_REQUIRED", fields={"name": "Name is required."}, Field="Name")
    await name_free(db, name)
    count = (await db.execute(select(func.count()).select_from(LabelType).where(LabelType.archived.is_(False)))
             ).scalar_one()
    if count >= MAX_TYPES:
        raise ApiError("INVALID_STATE")
    source = await current_default(db, (await resolve_type(db, body.copy_from_type_id)).id)
    last = (await db.execute(select(func.max(LabelType.sort_order)))).scalar_one()
    t = LabelType(name=name, sort_order=int(last or 0) + 1, created_by=user.id)
    db.add(t)
    await db.flush()
    cfg = LabelConfig(label_type_id=t.id, config_key=uuid.uuid4(), version=1, scope="default", part_id=None,
                      label_size_id=source.label_size_id, spec=source.spec, qr_mode=source.qr_mode,
                      serial_mode=source.serial_mode, serial_sequence_id=source.serial_sequence_id, created_by=user.id)
    db.add(cfg)
    await db.flush()
    audit(db, user.id, "label_type.create", "label_type", t.id, None,
          {"name": name, "copied_from_config": source.id, "config_id": cfg.id})
    await db.commit()
    return await type_out(db, t)


@router.patch("/label-types/{type_id}", response_model=LabelTypeOut)
async def update_type(type_id: uuid.UUID, body: TypePatch, user: Admin, db: DB) -> LabelTypeOut:
    t = await resolve_type(db, type_id)
    before = {"name": t.name, "sort_order": t.sort_order}
    if body.name is not None and body.name.strip() != t.name:
        await name_free(db, body.name.strip(), t.id)
        t.name = body.name.strip()
    if body.sort_order is not None:
        t.sort_order = body.sort_order
    audit(db, user.id, "label_type.update", "label_type", t.id, before, {"name": t.name, "sort_order": t.sort_order})
    await db.commit()
    return await type_out(db, t)


@router.post("/label-types/{type_id}/archive", status_code=204)
async def archive_type(type_id: uuid.UUID, user: Admin, db: DB) -> None:
    """Hides the type from Configure and Print. Its configs stay, so its print history and reprints are exact."""
    t = await resolve_type(db, type_id)
    active = (await db.execute(select(func.count()).select_from(LabelType).where(LabelType.archived.is_(False)))
              ).scalar_one()
    if active <= 1:
        raise ApiError("LABEL_TYPE_LAST")
    t.archived = True
    audit(db, user.id, "label_type.archive", "label_type", t.id, {"archived": False}, {"archived": True})
    await db.commit()
