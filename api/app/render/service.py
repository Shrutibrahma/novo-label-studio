"""Bridges database rows and the pure renderer: loads the part, config, size, printer; builds the snapshot."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.spec import LabelSpec, parse_spec
from app.errors import ApiError
from app.models import CustomFieldDef, LabelSize, Part, PartAlias, Printer, SerialSequence
from app.render.engine import RenderConfig, RenderPrinter, RenderResult, RenderSize, render
from app.render.snapshot import build_snapshot, clean_manual, field_labels, part_field_values


@dataclass
class RenderContext:
    printer: Printer
    custom_labels: dict[str, str]
    custom_keys: set[str]
    sequence: SerialSequence


@dataclass
class ConfigLike:
    """A stored label_config row or an unsaved draft from the Configure editor."""

    label_size_id: uuid.UUID
    spec: dict[str, Any]
    qr_mode: str
    serial_mode: str


async def render_context(db: AsyncSession, printer: Printer | None = None) -> RenderContext:
    if printer is None:
        printer = (await db.execute(select(Printer).where(Printer.is_default.is_(True)))).scalar_one_or_none()
        if printer is None:
            raise ApiError("NOT_FOUND")
    defs = (await db.execute(select(CustomFieldDef).where(CustomFieldDef.printable.is_(True)))).scalars().all()
    seq = (await db.execute(select(SerialSequence).where(SerialSequence.name == "Default"))).scalar_one()
    return RenderContext(printer=printer, custom_labels={d.key: d.label for d in defs},
                         custom_keys={d.key for d in defs}, sequence=seq)


def preview_serial(seq: SerialSequence) -> str:
    """7.7: prefix + separator + one 8 per configured digit (the widest digit), e.g. NOVO-88888888."""
    return f"{seq.prefix}{seq.separator}{'8' * seq.digits}"


async def label_name_of(db: AsyncSession, part_id: uuid.UUID) -> str | None:
    return (await db.execute(select(PartAlias.alias).where(PartAlias.part_id == part_id,
                                                           PartAlias.is_label_name.is_(True)))).scalar_one_or_none()


def part_values(part: Part, label_name: str | None) -> dict[str, Any]:
    return part_field_values(part.part_number, part.part_name, part.description, part.revision,
                             part.custom_data or {}, label_name)


def render_snapshot(snapshot: dict[str, Any], spec: LabelSpec, qr_mode: str, size: LabelSize, printer: Printer,
                    labels: dict[str, str]) -> RenderResult:
    return render(snapshot, RenderConfig(spec=spec, qr_mode=qr_mode, field_labels=labels),
                  RenderSize(width_in=size.width_in, height_in=size.height_in),
                  RenderPrinter(dpi=printer.dpi, print_width_in=printer.print_width_in))


async def render_part(db: AsyncSession, ctx: RenderContext, part: Part, cfg: ConfigLike,
                      manual_values: dict[str, Any] | None, print_date: str, serial: str | None
                      ) -> tuple[RenderResult, dict[str, Any], LabelSpec, LabelSize]:
    spec = parse_spec(cfg.spec)
    size = await db.get(LabelSize, cfg.label_size_id)
    if size is None:
        raise ApiError("NOT_FOUND")
    labels = field_labels(spec, ctx.custom_labels)
    manual = clean_manual(spec, manual_values, labels)
    snapshot = build_snapshot(spec, cfg.qr_mode, part_values(part, await label_name_of(db, part.id)),
                              ctx.custom_keys, manual, serial if cfg.serial_mode == "required" else None, print_date)
    return render_snapshot(snapshot, spec, cfg.qr_mode, size, ctx.printer, labels), snapshot, spec, size
