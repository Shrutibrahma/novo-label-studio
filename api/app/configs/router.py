"""Label configurations (D11; section 6; screens 12.6 "Show on label" and 12.11 Configure)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import audit
from app.auth.deps import DB, Admin, AnyUser
from app.configs.defaults import ALL_FONTS, SETTING_FONTS
from app.configs.effective import current_default, current_override, effective_config
from app.configs.spec import LabelSpec, SpecField, parse_spec, validate_spec
from app.errors import ApiError
from app.models import AppSetting, AppUser, CustomFieldDef, LabelConfig, LabelSize, Part, PartAlias, SerialSequence
from app.parts.router import SizeBrief, size_brief

router = APIRouter(tags=["configs"])

QrMode = Literal["none", "part", "serial"]
SerialMode = Literal["none", "required"]


class ConfigOut(BaseModel):
    id: str
    config_key: str
    version: int
    scope: str
    part_id: str | None
    size: SizeBrief
    spec: dict[str, Any]
    qr_mode: str
    serial_mode: str
    is_current: bool
    created_at: datetime
    created_by_name: str
    next_version: int


class DraftConfig(BaseModel):
    label_size_id: uuid.UUID
    spec: dict[str, Any]
    qr_mode: QrMode = "none"
    serial_mode: SerialMode = "none"


class PublishIn(DraftConfig):
    scope: Literal["default", "part"]
    part_id: uuid.UUID | None = None
    base_config_id: uuid.UUID | None = None


class SelectionIn(BaseModel):
    fields: list[SpecField] = Field(max_length=9)
    label_size_id: uuid.UUID
    emphasis: Literal["small", "medium", "large"]


class OverrideRow(BaseModel):
    config_id: str
    part_id: str
    part_number: str
    label_name: str | None
    size: SizeBrief
    version: int
    created_at: datetime
    created_by_name: str


class ConfigsList(BaseModel):
    default: ConfigOut
    overrides: list[OverrideRow]


async def config_out(db: AsyncSession, cfg: LabelConfig, next_version: int | None = None) -> ConfigOut:
    author = await db.get(AppUser, cfg.created_by)
    if next_version is None:
        latest = (await db.execute(select(func.max(LabelConfig.version))
                                   .where(LabelConfig.config_key == cfg.config_key))).scalar_one()
        next_version = int(latest or 0) + 1
    return ConfigOut(id=str(cfg.id), config_key=str(cfg.config_key), version=cfg.version, scope=cfg.scope,
                     part_id=str(cfg.part_id) if cfg.part_id else None, size=await size_brief(db, cfg.label_size_id),
                     spec=cfg.spec, qr_mode=cfg.qr_mode, serial_mode=cfg.serial_mode, is_current=cfg.is_current,
                     created_at=cfg.created_at, created_by_name=author.display_name if author else "",
                     next_version=next_version)


async def printable_custom_keys(db: AsyncSession) -> set[str]:
    return set((await db.execute(select(CustomFieldDef.key).where(CustomFieldDef.printable.is_(True)))).scalars())


async def allowed_fonts(db: AsyncSession) -> list[str]:
    row = await db.get(AppSetting, SETTING_FONTS)
    return list(row.value) if row is not None else list(ALL_FONTS)


async def checked_spec(db: AsyncSession, raw: dict[str, Any], qr_mode: str, serial_mode: str) -> LabelSpec:
    spec = parse_spec(raw)
    validate_spec(spec, await printable_custom_keys(db), qr_mode, serial_mode, await allowed_fonts(db))
    return spec


async def active_size(db: AsyncSession, size_id: uuid.UUID) -> LabelSize:
    size = await db.get(LabelSize, size_id)
    if size is None or not size.active:
        raise ApiError("NOT_FOUND")
    return size


async def publish(db: AsyncSession, user_id: uuid.UUID, scope: str, part_id: uuid.UUID | None, size_id: uuid.UUID,
                  spec: LabelSpec, qr_mode: str, serial_mode: str, base_config_id: uuid.UUID | None = None) -> LabelConfig:
    """Every change creates a new immutable version; the previous current version is retired (D11)."""
    await active_size(db, size_id)
    seq_id = None
    if serial_mode == "required":
        seq_id = (await db.execute(select(SerialSequence.id).where(SerialSequence.name == "Default"))).scalar_one()
    if scope == "default":
        current = (await db.execute(select(LabelConfig).where(LabelConfig.scope == "default",
                                                              LabelConfig.is_current.is_(True))
                                    .with_for_update())).scalar_one_or_none()
        if current is None:
            raise ApiError("NOT_FOUND")
        key, version = current.config_key, current.version + 1
    else:
        if part_id is None:
            raise ApiError("NOT_FOUND")
        part = await db.get(Part, part_id, with_for_update=True)  # serializes publishes for this part
        if part is None:
            raise ApiError("NOT_FOUND")
        current = await current_override(db, part_id)
        latest = (await db.execute(select(LabelConfig).where(LabelConfig.scope == "part",
                                                             LabelConfig.part_id == part_id)
                                   .order_by(LabelConfig.version.desc()).limit(1))).scalar_one_or_none()
        key = latest.config_key if latest else uuid.uuid4()
        version = latest.version + 1 if latest else 1
    if base_config_id is not None:
        effective = current if current is not None else (await current_default(db) if scope == "part" else None)
        if effective is None or effective.id != base_config_id:
            raise ApiError("STALE_WRITE")
    if current is not None:
        current.is_current = False
        await db.flush()
    spec_json = spec.model_dump(mode="json")
    cfg = LabelConfig(config_key=key, version=version, scope=scope, part_id=part_id if scope == "part" else None,
                      label_size_id=size_id, spec=spec_json, qr_mode=qr_mode, serial_mode=serial_mode,
                      serial_sequence_id=seq_id, created_by=user_id)
    db.add(cfg)
    await db.flush()
    audit(db, user_id, "config.publish", "label_config", cfg.id,
          {"config_id": current.id, "version": current.version} if current else None,
          {"scope": scope, "part_id": part_id, "version": version, "label_size_id": size_id, "spec": spec_json,
           "qr_mode": qr_mode, "serial_mode": serial_mode})
    return cfg


@router.get("/configs", response_model=ConfigsList)
async def list_configs(_: Admin, db: DB) -> ConfigsList:
    default = await current_default(db)
    rows = (await db.execute(
        select(LabelConfig, Part.part_number, PartAlias.alias, AppUser.display_name)
        .join(Part, Part.id == LabelConfig.part_id)
        .outerjoin(PartAlias, (PartAlias.part_id == Part.id) & PartAlias.is_label_name.is_(True))
        .join(AppUser, AppUser.id == LabelConfig.created_by)
        .where(LabelConfig.scope == "part", LabelConfig.is_current.is_(True))
        .order_by(func.upper(Part.part_number)))).all()
    overrides = [OverrideRow(config_id=str(c.id), part_id=str(c.part_id), part_number=pn, label_name=alias,
                             size=await size_brief(db, c.label_size_id), version=c.version, created_at=c.created_at,
                             created_by_name=who) for c, pn, alias, who in rows]
    return ConfigsList(default=await config_out(db, default), overrides=overrides)


@router.get("/configs/default", response_model=ConfigOut)
async def get_default(_: AnyUser, db: DB) -> ConfigOut:
    return await config_out(db, await current_default(db))


@router.get("/configs/{config_id}", response_model=ConfigOut)
async def get_config(config_id: uuid.UUID, _: AnyUser, db: DB) -> ConfigOut:
    cfg = await db.get(LabelConfig, config_id)
    if cfg is None:
        raise ApiError("NOT_FOUND")
    return await config_out(db, cfg)


@router.get("/parts/{part_id}/config", response_model=ConfigOut)
async def get_part_config(part_id: uuid.UUID, _: AnyUser, db: DB) -> ConfigOut:
    if await db.get(Part, part_id) is None:
        raise ApiError("NOT_FOUND")
    # next_version is the version a per-part publish would get (overrides keep counting after "Use default label").
    latest = (await db.execute(select(func.max(LabelConfig.version)).where(LabelConfig.scope == "part",
                                                                          LabelConfig.part_id == part_id))).scalar_one()
    return await config_out(db, await effective_config(db, part_id), next_version=int(latest or 0) + 1)


@router.post("/configs", response_model=ConfigOut, status_code=201)
async def publish_config(body: PublishIn, user: Admin, db: DB) -> ConfigOut:
    spec = await checked_spec(db, body.spec, body.qr_mode, body.serial_mode)
    cfg = await publish(db, user.id, body.scope, body.part_id, body.label_size_id, spec, body.qr_mode,
                        body.serial_mode, body.base_config_id)
    await db.commit()
    return await config_out(db, cfg)


@router.delete("/parts/{part_id}/config", response_model=ConfigOut)
async def use_default_label(part_id: uuid.UUID, user: Admin, db: DB) -> ConfigOut:
    """Retire the per-part override; the part falls back to the default ("Use default label")."""
    part = await db.get(Part, part_id, with_for_update=True)
    if part is None:
        raise ApiError("NOT_FOUND")
    override = await current_override(db, part_id)
    if override is not None:
        override.is_current = False
        audit(db, user.id, "config.publish", "label_config", override.id,
              {"config_id": override.id, "version": override.version}, {"retired": True, "part_id": part_id})
    await db.commit()
    return await config_out(db, await current_default(db))


@router.put("/parts/{part_id}/selection", response_model=ConfigOut)
async def save_selection(part_id: uuid.UUID, body: SelectionIn, user: AnyUser, db: DB) -> ConfigOut:
    """Any role: saves the Print dialog's field/size/text-size choice as a new per-part version. Everything else
    is copied from the part's effective config, so only these three keys can differ (section 6)."""
    if await db.get(Part, part_id) is None:
        raise ApiError("NOT_FOUND")
    effective = await effective_config(db, part_id)
    raw = dict(effective.spec)
    raw["fields"] = [f.model_dump() for f in body.fields]
    raw["style"] = dict(raw.get("style", {})) | {"emphasis": body.emphasis}
    spec = await checked_spec(db, raw, effective.qr_mode, effective.serial_mode)
    new_json = spec.model_dump(mode="json")
    if new_json == parse_spec(effective.spec).model_dump(mode="json") and body.label_size_id == effective.label_size_id:
        return await config_out(db, effective)
    cfg = await publish(db, user.id, "part", part_id, body.label_size_id, spec, effective.qr_mode, effective.serial_mode)
    await db.commit()
    return await config_out(db, cfg)
