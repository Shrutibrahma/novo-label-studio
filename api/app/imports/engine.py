"""Row validation (10.3) and diff (10.4). Pure functions over preloaded data, so a 50,000-row file is
checked without per-row queries."""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.imports.parse import number_as_text
from app.parts.values import (
    CORE_FIELDS,
    FieldDef,
    ValueError_,
    clean_text,
    is_blank,
    normalize_part_number,
    parse_custom,
)


IMAGE = "image"  # mapping target for pictures placed in cells (see mapping.IMAGE_TARGET)
NO_PICTURE = "This cell has no picture. Place the picture in the cell in Excel (.xlsx)."
BAD_PICTURE = "The picture in this cell can't be read. Use a PNG, JPEG or WebP picture."


@dataclass(frozen=True)
class StagedImage:
    """An image cell after the pictures were stored: the asset id, or why it can't be used."""

    asset_id: str | None = None
    error: str | None = None


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class ExistingPart:
    id: uuid.UUID
    part_number: str
    status: str
    values: dict[str, Any]  # core fields + custom data, keyed like mapping targets


@dataclass
class Context:
    defs: dict[str, FieldDef]
    targets: list[str]  # mapped targets, core and custom
    parts: dict[str, ExistingPart]  # by part_number_norm
    alias_owner: dict[str, str]  # upper(btrim(alias)) -> part number of the part that owns it


@dataclass
class RowResult:
    source_row: int | None
    action: str
    part_id: uuid.UUID | None
    data: dict[str, Any]
    diff: dict[str, list[Any]] | None
    errors: list[dict[str, str]] | None
    accepted: bool


@dataclass
class CleanRow:
    source_row: int
    data: dict[str, Any]
    errors: list[dict[str, str]] = field(default_factory=list)

    @property
    def number_norm(self) -> str | None:
        pn = self.data.get("part_number")
        return normalize_part_number(pn) if isinstance(pn, str) and pn.strip() else None


def raw_to_text(value: Any) -> str:
    if isinstance(value, int | float | Decimal) and not isinstance(value, bool):
        return number_as_text(value)
    return clean_text(value)


def clean(source_row: int, raw: dict[str, Any], ctx: Context) -> CleanRow:
    """Maps a row's cells to canonical values and records rule violations. Empty cells are dropped (they
    never clear an existing value), except that part_number / part_name presence is checked later."""
    data: dict[str, Any] = {}
    errors: list[dict[str, str]] = []
    for target in ctx.targets:
        value = raw.get(target)
        if is_blank(value):
            continue
        if target == IMAGE:
            # A stored picture (validation) or the asset id already staged (re-check after a row edit). An
            # empty cell never clears an existing image.
            if isinstance(value, StagedImage) and value.asset_id:
                data[IMAGE] = value.asset_id
            elif isinstance(value, str) and _is_uuid(value):
                data[IMAGE] = value
            else:
                errors.append({"field": IMAGE, "msg": value.error if isinstance(value, StagedImage) and value.error
                               else NO_PICTURE})
            continue
        if target in CORE_FIELDS:
            text = raw_to_text(value)
            label, max_len = CORE_FIELDS[target]
            if len(text) > max_len:
                errors.append({"field": target, "msg": f"{label} is longer than {max_len} characters."})
            data[target] = text
        else:
            fdef = ctx.defs[target]
            try:
                data[target] = parse_custom(fdef, value)
            except ValueError_ as err:
                errors.append({"field": target, "msg": err.message})
                data[target] = raw_to_text(value)
    if "part_number" not in data:
        errors.insert(0, {"field": "part_number", "msg": "Part number is missing."})
    return CleanRow(source_row=source_row, data=data, errors=errors)


def duplicate_rows(rows: list[CleanRow]) -> dict[str, list[int]]:
    by_number: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        if r.number_norm:
            by_number[r.number_norm].append(r.source_row)
    return {k: v for k, v in by_number.items() if len(v) > 1}


def _rows_text(rows: list[int]) -> str:
    return ", ".join(str(r) for r in sorted(rows))


def classify(row: CleanRow, ctx: Context, dups: dict[str, list[int]]) -> RowResult:
    errors = list(row.errors)
    norm = row.number_norm
    existing = ctx.parts.get(norm) if norm else None
    if norm and norm in dups:
        errors.append({"field": "part_number",
                       "msg": f"Duplicate part number in this file (rows {_rows_text(dups[norm])})."})
    if existing is None:
        if "part_name" not in row.data:
            errors.append({"field": "part_name", "msg": "Part name is missing."})
        for fdef in ctx.defs.values():
            if fdef.required and fdef.key not in row.data:
                errors.append({"field": fdef.key, "msg": f"{fdef.label} is required."})
        if norm and norm in ctx.alias_owner:
            errors.append({"field": "part_number", "msg": "This part number is already used as a label name "
                                                          f"for part {ctx.alias_owner[norm]}."})
    if errors:
        return RowResult(row.source_row, "invalid", existing.id if existing else None, row.data, None, errors, False)
    if existing is None:
        return RowResult(row.source_row, "new", None, row.data, None, None, True)

    diff: dict[str, list[Any]] = {}
    for key, value in row.data.items():
        if key == "part_number":
            continue  # matched on the normalized number; the stored spelling is kept
        if existing.values.get(key) != value:
            diff[key] = [existing.values.get(key), value]
    if existing.status == "archived":
        # Matches an archived part: an update flagged "Restore archived part", not accepted by default.
        diff["status"] = ["archived", "active"]
        return RowResult(row.source_row, "update", existing.id, row.data, diff, None, False)
    if existing.status == "inactive":
        diff["status"] = ["inactive", "active"]
    if not diff:
        return RowResult(row.source_row, "unchanged", existing.id, row.data, None, None, True)
    return RowResult(row.source_row, "update", existing.id, row.data, diff, None, True)


def missing_rows(ctx: Context, seen_numbers: set[str]) -> list[RowResult]:
    """Active parts that aren't in the file: proposed as inactive, not accepted by default (D9)."""
    out: list[RowResult] = []
    for norm, part in sorted(ctx.parts.items()):
        if part.status == "active" and norm not in seen_numbers:
            out.append(RowResult(None, "missing", part.id,
                                 {"part_number": part.part_number, "part_name": part.values.get("part_name")},
                                 None, None, False))
    return out


def evaluate(rows: list[tuple[int, dict[str, Any]]], ctx: Context) -> list[RowResult]:
    cleaned = [clean(n, raw, ctx) for n, raw in rows]
    dups = duplicate_rows(cleaned)
    results = [classify(r, ctx, dups) for r in cleaned]
    seen = {r.number_norm for r in cleaned if r.number_norm}
    return results + missing_rows(ctx, seen)


def core_values(part_number: str, part_name: str, description: str | None, revision: str | None,
                custom: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = dict(custom)
    values.update({"part_number": part_number, "part_name": part_name})
    if description is not None:
        values["description"] = description
    if revision is not None:
        values["revision"] = revision
    return values
