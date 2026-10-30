"""Bridges database rows and the pure renderer: loads the part, config, size, printer; builds the snapshot."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from PIL import Image, UnidentifiedImageError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.configs.spec import LabelSpec, parse_spec
from app.errors import ApiError
from app.configs.defaults import SETTING_COMPANY
from app.configs.effective import resolve_type
from app.models import AppSetting, Asset, CustomFieldDef, LabelSize, LabelType, Part, PartAlias, Printer, SerialSequence
from app.render.engine import RenderConfig, RenderPrinter, RenderResult, RenderSize, render
from app.render.house import HouseStyle, snapshot_style
from app.settings.router import house_style
from app.render.snapshot import build_snapshot, clean_manual, field_labels, part_field_values, quick_snapshot


@dataclass
class RenderContext:
    printer: Printer
    custom_labels: dict[str, str]
    custom_keys: set[str]
    sequence: SerialSequence
    house: HouseStyle
    company: str


@dataclass
class ConfigLike:
    """A stored label_config row or an unsaved draft from the Configure editor."""

    label_size_id: uuid.UUID
    spec: dict[str, Any]
    qr_mode: str
    serial_mode: str
    label_type_id: uuid.UUID | None = None  # the first type when None


async def render_context(db: AsyncSession, printer: Printer | None = None) -> RenderContext:
    if printer is None:
        printer = (await db.execute(select(Printer).where(Printer.is_default.is_(True)))).scalar_one_or_none()
        if printer is None:
            raise ApiError("NOT_FOUND")
    defs = (await db.execute(select(CustomFieldDef).where(CustomFieldDef.printable.is_(True)))).scalars().all()
    seq = (await db.execute(select(SerialSequence).where(SerialSequence.name == "Default"))).scalar_one()
    company = await db.get(AppSetting, SETTING_COMPANY)
    return RenderContext(printer=printer, custom_labels={d.key: d.label for d in defs},
                         custom_keys={d.key for d in defs}, sequence=seq, house=await house_style(db),
                         company=str(company.value) if company is not None else "")


def house_snapshot(ctx: RenderContext, label_type: LabelType, spec: LabelSpec,
                   style: HouseStyle | None = None) -> dict[str, Any]:
    """generated.house_style for a label of `label_type`. The band shows the type's title (its name when not
    set); a bin-layout design shows its own title there instead (v1.1 4.2)."""
    title = spec.bin.title if spec.style.layout == "bin" else (label_type.title or label_type.name)
    return snapshot_style(style or ctx.house, title.strip(), ctx.company)


async def type_of(db: AsyncSession, type_id: uuid.UUID | None) -> LabelType:
    t = await db.get(LabelType, type_id) if type_id is not None else None
    return t if t is not None else await resolve_type(db, None)


def preview_serial(seq: SerialSequence) -> str:
    """7.7: prefix + separator + one 8 per configured digit (the widest digit), e.g. NOVO-88888888."""
    return f"{seq.prefix}{seq.separator}{'8' * seq.digits}"


async def label_name_of(db: AsyncSession, part_id: uuid.UUID) -> str | None:
    return (await db.execute(select(PartAlias.alias).where(PartAlias.part_id == part_id,
                                                           PartAlias.is_label_name.is_(True)))).scalar_one_or_none()


async def image_of(db: AsyncSession, part: Part) -> tuple[str, str] | None:
    """(asset id, sha256 hex) of the part's picture."""
    if part.image_asset_id is None:
        return None
    asset = await db.get(Asset, part.image_asset_id)
    return (str(asset.id), asset.sha256.hex()) if asset else None


def part_values(part: Part, label_name: str | None, image: tuple[str, str] | None = None) -> dict[str, Any]:
    return part_field_values(part.part_number, part.part_name, part.description, part.revision,
                             part.custom_data or {}, label_name, image)


@lru_cache(maxsize=64)
def _load_picture(sha_hex: str) -> Image.Image | None:
    path = get_settings().asset_dir / sha_hex[:2] / f"{sha_hex}.png"
    try:
        with Image.open(path) as img:
            img.load()
            return img.copy()
    except (OSError, UnidentifiedImageError):
        return None


def snapshot_picture(snapshot: dict[str, Any]) -> Image.Image | None:
    sha = snapshot.get("generated", {}).get("image_sha256")
    return _load_picture(sha) if isinstance(sha, str) and len(sha) == 64 else None


def render_snapshot(snapshot: dict[str, Any], spec: LabelSpec, qr_mode: str, size: LabelSize, printer: Printer,
                    labels: dict[str, str]) -> RenderResult:
    return render(snapshot, RenderConfig(spec=spec, qr_mode=qr_mode, field_labels=labels),
                  RenderSize(width_in=size.width_in, height_in=size.height_in),
                  RenderPrinter(dpi=printer.dpi, print_width_in=printer.print_width_in), snapshot_picture(snapshot))


async def render_quick(db: AsyncSession, ctx: RenderContext, label_type: LabelType, cfg: ConfigLike,
                       manual_values: dict[str, Any] | None, print_date: str, house: HouseStyle | None = None
                       ) -> tuple[RenderResult, dict[str, Any], LabelSpec, LabelSize]:
    """A quick label of `label_type` (no part)."""
    spec = parse_spec(cfg.spec)
    size = await db.get(LabelSize, cfg.label_size_id)
    if size is None:
        raise ApiError("NOT_FOUND")
    labels = field_labels(spec, ctx.custom_labels)
    snapshot = quick_snapshot(clean_manual(spec, manual_values, labels), print_date,
                              house_snapshot(ctx, label_type, spec, house))
    return render_snapshot(snapshot, spec, "none", size, ctx.printer, labels), snapshot, spec, size


async def render_part(db: AsyncSession, ctx: RenderContext, part: Part, cfg: ConfigLike,
                      manual_values: dict[str, Any] | None, print_date: str, serial: str | None,
                      house: HouseStyle | None = None) -> tuple[RenderResult, dict[str, Any], LabelSpec, LabelSize]:
    """`house` replaces the saved house style (the Settings → Label style draft)."""
    spec = parse_spec(cfg.spec)
    size = await db.get(LabelSize, cfg.label_size_id)
    if size is None:
        raise ApiError("NOT_FOUND")
    labels = field_labels(spec, ctx.custom_labels)
    manual = clean_manual(spec, manual_values, labels)
    snapshot = build_snapshot(spec, cfg.qr_mode, part_values(part, await label_name_of(db, part.id),
                                                             await image_of(db, part)),
                              ctx.custom_keys, manual, serial if cfg.serial_mode == "required" else None, print_date,
                              labels, house_snapshot(ctx, await type_of(db, cfg.label_type_id), spec, house))
    return render_snapshot(snapshot, spec, cfg.qr_mode, size, ctx.printer, labels), snapshot, spec, size
