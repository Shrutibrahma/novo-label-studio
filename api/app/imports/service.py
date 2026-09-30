"""Import pipeline work: parse in the background, validate + diff with progress, and commit (section 10)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from anyio import to_thread
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.sessions import now_utc
from app.config import get_settings
from app.db import sessionmaker
from app.imports.engine import (
    CleanRow,
    Context,
    ExistingPart,
    RowResult,
    classify,
    clean,
    duplicate_rows,
    missing_rows,
    raw_to_text,
)
from app.imports.mapping import signature, suggest
from app.imports.parse import ParseError, Sheet, file_kind, read_file
from app.models import CustomFieldDef, ImportBatch, ImportMapping, ImportRow, Part, PartAlias
from app.parts.values import FieldDef

log = logging.getLogger("app.imports")

EXPIRY = timedelta(hours=24)
OPEN_STATUSES = ("parsing", "needs_sheet", "mapping", "validating", "staged")
CHUNK = 500


@dataclass
class Meta:
    sheets: list[tuple[str, int]]
    headers: list[str]
    samples: dict[str, list[str]]


_meta: dict[uuid.UUID, Meta] = {}
_tasks: dict[uuid.UUID, asyncio.Task[None]] = {}


def upload_dir() -> Path:
    d = get_settings().asset_dir / "imports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def stored_path(batch: ImportBatch) -> Path:
    return upload_dir() / f"{batch.id}{Path(batch.file_name).suffix.lower()}"


def remove_file(batch: ImportBatch) -> None:
    stored_path(batch).unlink(missing_ok=True)
    _meta.pop(batch.id, None)


def _samples(sheet: Sheet) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {h: [] for h in sheet.headers}
    for _, cells in sheet.rows:
        for h, v in zip(sheet.headers, cells, strict=False):
            if v is not None and len(out[h]) < 3:
                out[h].append(raw_to_text(v))
        if all(len(v) >= 3 for v in out.values()):
            break
    return out


def _read_sheets(path: Path, name: str, only: str | None) -> list[Sheet]:
    return read_file(path, file_kind(name), only)


async def _set(batch_id: uuid.UUID, **values: Any) -> None:
    async with sessionmaker()() as db:
        await db.execute(update(ImportBatch).where(ImportBatch.id == batch_id).values(**values))
        await db.commit()


def spawn(batch_id: uuid.UUID, coro: Any) -> None:
    task = asyncio.create_task(coro, name=f"import-{batch_id}")
    _tasks[batch_id] = task
    task.add_done_callback(lambda t: _tasks.pop(batch_id, None) if _tasks.get(batch_id) is t else None)


async def wait_idle(batch_id: uuid.UUID) -> None:
    """Tests use this to wait for the background step of a batch."""
    task = _tasks.get(batch_id)
    if task is not None:
        await asyncio.shield(task)


# ---------------------------------------------------------------- step 1: read the file
async def parse_upload(batch_id: uuid.UUID, file_name: str) -> None:
    path = upload_dir() / f"{batch_id}{Path(file_name).suffix.lower()}"
    try:
        sheets = await to_thread.run_sync(_read_sheets, path, file_name, None)
    except ParseError as err:
        await _set(batch_id, status="failed", error=err.code)
        return
    except Exception:
        log.exception("import %s: parse failed", batch_id)
        await _set(batch_id, status="failed", error="FILE_UNREADABLE")
        return
    listing = [(s.name, len(s.rows)) for s in sheets]
    if len(sheets) > 1:
        _meta[batch_id] = Meta(sheets=listing, headers=[], samples={})
        await _set(batch_id, status="needs_sheet")
        return
    sheet = sheets[0]
    _meta[batch_id] = Meta(sheets=listing, headers=sheet.headers, samples=_samples(sheet))
    await _set(batch_id, status="mapping", sheet_name=sheet.name or None, total_rows=len(sheet.rows))


async def choose_sheet(batch_id: uuid.UUID, file_name: str, sheet_name: str) -> None:
    path = upload_dir() / f"{batch_id}{Path(file_name).suffix.lower()}"
    try:
        sheets = await to_thread.run_sync(_read_sheets, path, file_name, sheet_name)
    except ParseError as err:
        await _set(batch_id, status="failed", error=err.code)
        return
    sheet = sheets[0]
    listing = _meta.get(batch_id).sheets if batch_id in _meta else [(sheet.name, len(sheet.rows))]
    _meta[batch_id] = Meta(sheets=listing, headers=sheet.headers, samples=_samples(sheet))
    await _set(batch_id, status="mapping", sheet_name=sheet.name, total_rows=len(sheet.rows))


async def meta_for(batch: ImportBatch) -> Meta | None:
    """Headers/samples for the mapping step; rebuilt from the stored file after an API restart."""
    if batch.id in _meta:
        return _meta[batch.id]
    if batch.status not in ("needs_sheet", "mapping", "validating", "staged"):
        return None
    try:
        sheets = await to_thread.run_sync(_read_sheets, stored_path(batch), batch.file_name, batch.sheet_name)
    except ParseError:
        return None
    if batch.status == "needs_sheet":
        meta = Meta(sheets=[(s.name, len(s.rows)) for s in sheets], headers=[], samples={})
    else:
        s = sheets[0]
        meta = Meta(sheets=[(s.name, len(s.rows))], headers=s.headers, samples=_samples(s))
    _meta[batch.id] = meta
    return meta


# ---------------------------------------------------------------- mapping
async def custom_defs(db: AsyncSession) -> dict[str, FieldDef]:
    rows = (await db.execute(select(CustomFieldDef).order_by(CustomFieldDef.sort_order))).scalars()
    return {f.key: FieldDef(key=f.key, label=f.label, data_type=f.data_type, choices=tuple(f.choices or ()),
                            required=f.required) for f in rows}


async def suggested_mapping(db: AsyncSession, headers: list[str]) -> tuple[dict[str, str | None], str | None]:
    """Saved mapping for the header signature if one exists (with its name), else synonym suggestions."""
    saved = (await db.execute(select(ImportMapping).where(ImportMapping.header_signature == signature(headers)))
             ).scalar_one_or_none()
    defs = await custom_defs(db)
    if saved is not None:
        valid = set(defs) | {"part_number", "part_name", "description", "revision"}
        return {h: (saved.mapping.get(h) if saved.mapping.get(h) in valid else None) for h in headers}, saved.name
    return suggest(headers, [(d.key, d.label) for d in defs.values()]), None


# ---------------------------------------------------------------- step 2: validate + diff
async def load_context(db: AsyncSession, targets: list[str]) -> Context:
    defs = await custom_defs(db)
    parts: dict[str, ExistingPart] = {}
    rows = await db.execute(select(Part.id, Part.part_number, Part.part_number_norm, Part.part_name, Part.description,
                                   Part.revision, Part.custom_data, Part.status))
    for r in rows:
        values: dict[str, Any] = dict(r.custom_data or {})
        values["part_number"] = r.part_number
        values["part_name"] = r.part_name
        if r.description is not None:
            values["description"] = r.description
        if r.revision is not None:
            values["revision"] = r.revision
        parts[r.part_number_norm] = ExistingPart(id=r.id, part_number=r.part_number, status=r.status, values=values)
    owners = await db.execute(select(func.upper(func.btrim(PartAlias.alias)), Part.part_number)
                              .join(Part, Part.id == PartAlias.part_id))
    alias_owner = {a: pn for a, pn in owners}
    return Context(defs=defs, targets=targets, parts=parts, alias_owner=alias_owner)


def raw_rows(sheet: Sheet, mapping: dict[str, str | None]) -> list[tuple[int, dict[str, Any]]]:
    index = {target: sheet.headers.index(h) for h, target in mapping.items() if target and h in sheet.headers}
    return [(n, {t: cells[i] for t, i in index.items()}) for n, cells in sheet.rows]


def _json(value: Any) -> str | None:
    return None if value is None else json.dumps(value)


async def copy_records(db: AsyncSession, table: str, columns: list[str], records: list[tuple[Any, ...]]) -> None:
    """Bulk write with COPY on the session's own connection (same transaction). jsonb values are JSON strings.
    A batched INSERT costs a network round trip per row through Docker Desktop; COPY streams them."""
    if not records:
        return
    conn = await db.connection()
    raw = await conn.get_raw_connection()
    await raw.driver_connection.copy_records_to_table(table, records=records, columns=columns)  # type: ignore[union-attr]


IMPORT_ROW_COLUMNS = ["batch_id", "source_row", "action", "part_id", "data", "diff", "errors", "accepted"]


def row_record(batch_id: uuid.UUID, r: RowResult) -> tuple[Any, ...]:
    return (batch_id, r.source_row, r.action, r.part_id, json.dumps(r.data), _json(r.diff), _json(r.errors), r.accepted)


async def recount(db: AsyncSession, batch_id: uuid.UUID) -> None:
    counts = dict((await db.execute(select(ImportRow.action, func.count()).where(ImportRow.batch_id == batch_id)
                                    .group_by(ImportRow.action))).all())
    await db.execute(update(ImportBatch).where(ImportBatch.id == batch_id).values(
        new_count=counts.get("new", 0), updated_count=counts.get("update", 0),
        unchanged_count=counts.get("unchanged", 0), invalid_count=counts.get("invalid", 0),
        missing_count=counts.get("missing", 0)))


async def validate(batch_id: uuid.UUID, mapping: dict[str, str | None]) -> None:
    t0 = time.perf_counter()
    try:
        async with sessionmaker()() as db:
            batch = await db.get(ImportBatch, batch_id)
            assert batch is not None
            sheets = await to_thread.run_sync(_read_sheets, stored_path(batch), batch.file_name, batch.sheet_name)
            log.info("import %s: read %d rows in %.1f s", batch_id, len(sheets[0].rows), time.perf_counter() - t0)
            sheet = sheets[0]
            targets = [t for t in mapping.values() if t]
            ctx = await load_context(db, targets)
            rows = raw_rows(sheet, mapping)
        total = len(rows)
        await _set(batch_id, progress_total=total, progress_done=0, total_rows=total)

        # Validation is CPU work: run it off the event loop, reporting progress between chunks.
        cleaned: list[CleanRow] = []
        for start in range(0, total, CHUNK):
            chunk = rows[start:start + CHUNK]
            cleaned += await to_thread.run_sync(lambda c=chunk: [clean(n, raw, ctx) for n, raw in c])
            await _set(batch_id, progress_done=min(total, start + CHUNK))
        dups = duplicate_rows(cleaned)
        results: list[RowResult] = await to_thread.run_sync(lambda: [classify(r, ctx, dups) for r in cleaned])
        seen = {r.number_norm for r in cleaned if r.number_norm}
        results += missing_rows(ctx, seen)
        log.info("import %s: validated + diffed at %.1f s", batch_id, time.perf_counter() - t0)

        async with sessionmaker()() as db:
            await db.execute(delete(ImportRow).where(ImportRow.batch_id == batch_id))
            await copy_records(db, "import_row", IMPORT_ROW_COLUMNS, [row_record(batch_id, r) for r in results])
            await recount(db, batch_id)
            await db.execute(update(ImportBatch).where(ImportBatch.id == batch_id)
                             .values(status="staged", progress_done=total))
            await db.commit()
        log.info("import %s: staged %d rows at %.1f s", batch_id, len(results), time.perf_counter() - t0)
    except ParseError as err:
        await _set(batch_id, status="failed", error=err.code)
    except Exception:
        log.exception("import %s: validation failed", batch_id)
        await _set(batch_id, status="failed", error="FILE_UNREADABLE")


# ---------------------------------------------------------------- scheduled expiry
async def expire_batches(db: AsyncSession) -> None:
    """Staged batches not committed within 24 hours are discarded (10.5)."""
    cutoff = now_utc() - EXPIRY
    stale = (await db.execute(select(ImportBatch).where(ImportBatch.status.in_(OPEN_STATUSES),
                                                        ImportBatch.created_at < cutoff))).scalars().all()
    for batch in stale:
        if batch.id in _tasks:
            continue
        batch.status = "discarded"
        await db.execute(delete(ImportRow).where(ImportRow.batch_id == batch.id))
        remove_file(batch)


async def locked_batch(db: AsyncSession, batch_id: uuid.UUID) -> ImportBatch | None:
    return (await db.execute(select(ImportBatch).where(ImportBatch.id == batch_id).with_for_update())).scalar_one_or_none()


async def lock_parts_table(db: AsyncSession) -> None:
    # Serializes concurrent commits against manual part creation just long enough to keep the diff valid.
    await db.execute(text("LOCK TABLE part IN SHARE ROW EXCLUSIVE MODE"))
