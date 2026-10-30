"""Saved label types (migration 0003): Label, Bin, Rack, Workstation, Kanban, ... each with its own versioned
default design and per-part overrides. Printing picks a type."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.audit import audit
from app.auth.deps import DB, Admin, AnyUser
from app.configs.effective import current_default, resolve_type
from app.errors import ApiError
from app.models import CustomFieldDef, LabelConfig, LabelSize, LabelType, SerialSequence
from app.configs.presets import PRESETS, preset_spec
from app.configs.spec import parse_spec, validate_quick
from app.configs.router import checked_spec
from app.parts.router import SizeBrief, size_brief
from app.render.house import TITLE_MAX

router = APIRouter(tags=["label types"])

MAX_TYPES = 30
# Kinds a new type can be created as (quick labels arrive with v1.1 U4).
CREATABLE_KINDS = ("part", "quick")


class LabelTypeOut(BaseModel):
    id: str
    name: str
    kind: str  # part | quick (v1.1 D24)
    title: str | None  # printed in the title band; None = the name
    sort_order: int
    size: SizeBrief
    layout: str
    version: int
    default_config_id: str
    override_count: int
    created_at: datetime


class TypeIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    title: str | None = Field(default=None, max_length=40)
    copy_from_type_id: uuid.UUID | None = None
    preset: str | None = None  # start from an industrial preset (v1.1 D22) instead of a copy
    kind: Literal["part", "quick"] = "part"  # chosen once, at creation (v1.1 7.2)


class PresetOut(BaseModel):
    key: str
    name: str
    size_name: str
    kind: str


def clean_title(raw: str | None) -> str | None:
    """Trimmed; empty means none (the band shows the name). At most 24 characters."""
    title = (raw or "").strip()
    if len(title) > TITLE_MAX:
        raise ApiError("FIELD_TOO_LONG", fields={"title": f"Title on label is longer than {TITLE_MAX} characters."},
                       Field="Title on label", max=TITLE_MAX)
    return title or None


class TypePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    sort_order: int | None = Field(default=None, ge=0, le=1000)
    title: str | None = Field(default=None, max_length=40)  # trimmed, then at most 24; null or empty clears it


async def type_out(db: DB, t: LabelType) -> LabelTypeOut:
    cfg = await current_default(db, t.id)
    overrides = (await db.execute(select(func.count()).select_from(LabelConfig).where(
        LabelConfig.label_type_id == t.id, LabelConfig.scope == "part", LabelConfig.is_current.is_(True)))).scalar_one()
    return LabelTypeOut(id=str(t.id), name=t.name, kind=t.kind, title=t.title, sort_order=t.sort_order, size=await size_brief(db, cfg.label_size_id),
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


@router.get("/label-types/presets", response_model=list[PresetOut])
async def list_presets(_: Admin) -> list[PresetOut]:
    return [PresetOut(key=p.key, name=p.name, size_name=p.size_name, kind=p.kind) for p in PRESETS
            if p.kind in CREATABLE_KINDS]


async def preset_config(db: DB, key: str) -> tuple[uuid.UUID, dict[str, Any], str, str, uuid.UUID | None]:
    """(size id, spec, qr mode, serial mode, serial sequence) for a preset; boxes find custom fields by name."""
    p = next((x for x in PRESETS if x.key == key and x.kind in CREATABLE_KINDS), None)
    if p is None:
        raise ApiError("NOT_FOUND")
    size = (await db.execute(select(LabelSize).where(LabelSize.name == p.size_name, LabelSize.active.is_(True)))
            ).scalar_one_or_none()
    if size is None:
        raise ApiError("NOT_FOUND")
    defs = (await db.execute(select(CustomFieldDef).where(CustomFieldDef.printable.is_(True))
                             .order_by(CustomFieldDef.sort_order, CustomFieldDef.key))).scalars().all()
    spec = preset_spec(p, [(d.key, d.label) for d in defs])
    parsed = await checked_spec(db, spec, p.qr_mode, p.serial_mode)
    if p.kind == "quick":
        validate_quick(parsed, p.qr_mode, p.serial_mode)
    seq = None
    if p.serial_mode == "required":
        seq = (await db.execute(select(SerialSequence.id).where(SerialSequence.name == "Default"))).scalar_one()
    return size.id, spec, p.qr_mode, p.serial_mode, seq


@router.post("/label-types", response_model=LabelTypeOut, status_code=201)
async def create_type(body: TypeIn, user: Admin, db: DB) -> LabelTypeOut:
    """A new type starts from an industrial preset, or as a copy of another type's current default design (the
    first type when neither is given)."""
    name = body.name.strip()
    if not name:
        raise ApiError("FIELD_REQUIRED", fields={"name": "Name is required."}, Field="Name")
    await name_free(db, name)
    count = (await db.execute(select(func.count()).select_from(LabelType).where(LabelType.archived.is_(False)))
             ).scalar_one()
    if count >= MAX_TYPES:
        raise ApiError("INVALID_STATE")
    if body.preset:
        size_id, spec, qr_mode, serial_mode, seq_id = await preset_config(db, body.preset)
        origin: dict[str, Any] = {"preset": body.preset}
        if next(p.kind for p in PRESETS if p.key == body.preset) != body.kind:
            raise ApiError("QUICK_LABEL_INVALID")
    else:
        source = await current_default(db, (await resolve_type(db, body.copy_from_type_id)).id)
        if body.kind == "quick":
            validate_quick(parse_spec(source.spec), source.qr_mode, source.serial_mode)
        size_id, spec, qr_mode, serial_mode, seq_id = (source.label_size_id, source.spec, source.qr_mode,
                                                       source.serial_mode, source.serial_sequence_id)
        origin = {"copied_from_config": source.id}
    last = (await db.execute(select(func.max(LabelType.sort_order)))).scalar_one()
    t = LabelType(name=name, kind=body.kind, title=clean_title(body.title), sort_order=int(last or 0) + 1, created_by=user.id)
    db.add(t)
    await db.flush()
    cfg = LabelConfig(label_type_id=t.id, config_key=uuid.uuid4(), version=1, scope="default", part_id=None,
                      label_size_id=size_id, spec=spec, qr_mode=qr_mode, serial_mode=serial_mode,
                      serial_sequence_id=seq_id, created_by=user.id)
    db.add(cfg)
    await db.flush()
    audit(db, user.id, "label_type.create", "label_type", t.id, None,
          {"name": name, **origin, "config_id": cfg.id})
    await db.commit()
    return await type_out(db, t)


@router.patch("/label-types/{type_id}", response_model=LabelTypeOut)
async def update_type(type_id: uuid.UUID, body: TypePatch, user: Admin, db: DB) -> LabelTypeOut:
    t = await resolve_type(db, type_id)
    before = {"name": t.name, "sort_order": t.sort_order, "title": t.title}
    if body.name is not None and body.name.strip() != t.name:
        await name_free(db, body.name.strip(), t.id)
        t.name = body.name.strip()
    if body.sort_order is not None:
        t.sort_order = body.sort_order
    if "title" in body.model_fields_set:
        t.title = clean_title(body.title)
    audit(db, user.id, "label_type.update", "label_type", t.id, before,
          {"name": t.name, "sort_order": t.sort_order, "title": t.title})
    await db.commit()
    return await type_out(db, t)


@router.post("/label-types/{type_id}/archive", status_code=204)
async def archive_type(type_id: uuid.UUID, user: Admin, db: DB) -> None:
    """Hides the type from Configure and Print. Its configs stay, so its print history and reprints are exact."""
    t = await resolve_type(db, type_id)
    if t.kind == "part":
        active = (await db.execute(select(func.count()).select_from(LabelType).where(
            LabelType.archived.is_(False), LabelType.kind == "part"))).scalar_one()
        if active <= 1:
            raise ApiError("LABEL_TYPE_LAST")  # parts always need a type to print as
    t.archived = True
    audit(db, user.id, "label_type.archive", "label_type", t.id, {"archived": False}, {"archived": True})
    await db.commit()
