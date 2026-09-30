"""POST /imports, PUT /imports/{id}/sheet|mapping, GET/PATCH rows, commit, discard (section 6, 10, 12.10)."""

from __future__ import annotations

import hashlib
import json
import uuid

import asyncpg
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import audit
from app.auth.deps import DB, Admin
from app.auth.sessions import now_utc
from app.errors import ApiError, message_for
from app.imports import service
from app.imports.engine import classify, clean, duplicate_rows
from app.imports.mapping import CORE_TARGETS, IMAGE_TARGET, signature
from app.imports.parse import MAX_FILE_BYTES, ParseError, file_kind
from app.models import ImportBatch, ImportMapping, ImportRow, Part
from app.parts.values import normalize_part_number

router = APIRouter(prefix="/imports", tags=["imports"])

NEW_PART_COLUMNS = ["part_number", "part_name", "description", "revision", "custom_data", "status", "source",
                    "last_import_batch_id", "created_by", "updated_by", "image_asset_id"]
CORE_KEYS = ("part_number", "part_name", "description", "revision", IMAGE_TARGET)


def _image_id(data: dict[str, Any]) -> uuid.UUID | None:
    value = data.get(IMAGE_TARGET)
    return uuid.UUID(value) if isinstance(value, str) else None

Action = Literal["new", "update", "unchanged", "invalid", "missing"]


class SheetOut(BaseModel):
    name: str
    rows: int


class ColumnOut(BaseModel):
    header: str
    samples: list[str]


class Counts(BaseModel):
    total_rows: int
    new: int
    updated: int
    unchanged: int
    invalid: int
    missing: int


class BatchOut(BaseModel):
    id: str
    file_name: str
    status: str
    error: dict[str, str] | None
    sheet_name: str | None
    sheets: list[SheetOut]
    columns: list[ColumnOut]
    mapping: dict[str, str | None]
    saved_mapping_name: str | None
    save_as_default: str
    progress_done: int
    progress_total: int
    counts: Counts
    accepted_to_import: int
    accepted_missing: int
    created_at: datetime
    committed_at: datetime | None


class RowOut(BaseModel):
    id: int
    source_row: int | None
    action: str
    part_id: str | None
    data: dict[str, Any]
    diff: dict[str, list[Any]] | None
    errors: list[dict[str, str]] | None
    accepted: bool


class RowPage(BaseModel):
    items: list[RowOut]
    next_cursor: str | None


class SheetIn(BaseModel):
    sheet_name: str = Field(min_length=0, max_length=255)


class MappingIn(BaseModel):
    mapping: dict[str, str | None]
    save_as: str | None = Field(default=None, max_length=120)


class RowPatch(BaseModel):
    data: dict[str, Any] | None = None
    accepted: bool | None = None


class CommitOut(BaseModel):
    new: int
    updated: int
    marked_inactive: int
    skipped: int
    batch: BatchOut


# ---------------------------------------------------------------- helpers
def _expired(batch: ImportBatch) -> bool:
    return batch.status == "discarded" or (batch.status in service.OPEN_STATUSES
                                           and now_utc() - batch.created_at > service.EXPIRY)


async def open_batch(db: AsyncSession, batch_id: uuid.UUID, lock: bool = False) -> ImportBatch:
    batch = await service.locked_batch(db, batch_id) if lock else await db.get(ImportBatch, batch_id)
    if batch is None:
        raise ApiError("NOT_FOUND")
    if _expired(batch):
        raise ApiError("IMPORT_EXPIRED")
    return batch


async def batch_out(db: AsyncSession, batch: ImportBatch) -> BatchOut:
    meta = await service.meta_for(batch)
    mapping: dict[str, str | None] = {}
    saved_name: str | None = None
    columns: list[ColumnOut] = []
    if meta and meta.headers:
        columns = [ColumnOut(header=h, samples=meta.samples.get(h, [])) for h in meta.headers]
        if batch.mapping_id:
            saved = await db.get(ImportMapping, batch.mapping_id)
            if saved is not None:
                mapping = {h: saved.mapping.get(h) for h in meta.headers}
                saved_name = saved.name
        else:
            mapping, saved_name = await service.suggested_mapping(db, meta.headers, meta.pictures)
    accepted = dict((await db.execute(
        select(ImportRow.action, func.count()).where(ImportRow.batch_id == batch.id, ImportRow.accepted.is_(True),
                                                     ImportRow.action.in_(("new", "update", "missing")))
        .group_by(ImportRow.action))).all())
    error = None
    if batch.error:
        code = batch.error if batch.error in ("FILE_TOO_LARGE", "FILE_UNREADABLE", "FILE_NO_HEADER",
                                              "FILE_UNSUPPORTED") else "FILE_UNREADABLE"
        error = {"code": code, "message": message_for(code)}
    return BatchOut(
        id=str(batch.id), file_name=batch.file_name, status=batch.status, error=error, sheet_name=batch.sheet_name,
        sheets=[SheetOut(name=n, rows=c) for n, c in (meta.sheets if meta else [])], columns=columns,
        mapping=mapping, saved_mapping_name=saved_name, save_as_default=Path(batch.file_name).stem,
        progress_done=batch.progress_done, progress_total=batch.progress_total,
        counts=Counts(total_rows=batch.total_rows, new=batch.new_count, updated=batch.updated_count,
                      unchanged=batch.unchanged_count, invalid=batch.invalid_count, missing=batch.missing_count),
        accepted_to_import=accepted.get("new", 0) + accepted.get("update", 0),
        accepted_missing=accepted.get("missing", 0), created_at=batch.created_at, committed_at=batch.committed_at,
    )


def row_out(r: ImportRow) -> RowOut:
    return RowOut(id=r.id, source_row=r.source_row, action=r.action, part_id=str(r.part_id) if r.part_id else None,
                  data=r.data, diff=r.diff, errors=r.errors, accepted=r.accepted)


# ---------------------------------------------------------------- upload
@router.post("", response_model=BatchOut, status_code=201)
async def upload(user: Admin, db: DB, file: Annotated[UploadFile, File()]) -> BatchOut:
    name = Path(file.filename or "").name or "upload"
    try:
        file_kind(name)
    except ParseError as err:
        raise ApiError(err.code) from err
    data = await file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ApiError("FILE_TOO_LARGE")
    if not data:
        raise ApiError("FILE_NO_HEADER")
    batch = ImportBatch(file_name=name, file_sha256=hashlib.sha256(data).digest(), status="parsing", created_by=user.id)
    db.add(batch)
    await db.flush()
    path = service.stored_path(batch)
    path.write_bytes(data)
    await db.commit()
    service.spawn(batch.id, service.parse_upload(batch.id, name))
    return await batch_out(db, batch)


@router.get("/{batch_id}", response_model=BatchOut)
async def read_batch(batch_id: uuid.UUID, _: Admin, db: DB) -> BatchOut:
    batch = await db.get(ImportBatch, batch_id)
    if batch is None:
        raise ApiError("NOT_FOUND")
    if _expired(batch):
        raise ApiError("IMPORT_EXPIRED")
    return await batch_out(db, batch)


@router.put("/{batch_id}/sheet", response_model=BatchOut)
async def pick_sheet(batch_id: uuid.UUID, body: SheetIn, _: Admin, db: DB) -> BatchOut:
    batch = await open_batch(db, batch_id, lock=True)
    meta = await service.meta_for(batch)
    if batch.status not in ("needs_sheet", "mapping") or meta is None or body.sheet_name not in [n for n, _ in meta.sheets]:
        raise ApiError("INVALID_STATE")
    batch.status = "parsing"
    batch.mapping_id = None
    await db.commit()
    service.spawn(batch.id, service.choose_sheet(batch.id, batch.file_name, body.sheet_name))
    return await batch_out(db, batch)


# ---------------------------------------------------------------- mapping
@router.put("/{batch_id}/mapping", response_model=BatchOut)
async def confirm_mapping(batch_id: uuid.UUID, body: MappingIn, user: Admin, db: DB) -> BatchOut:
    batch = await open_batch(db, batch_id, lock=True)
    if batch.status not in ("mapping", "staged"):
        raise ApiError("INVALID_STATE")
    meta = await service.meta_for(batch)
    if meta is None or not meta.headers:
        raise ApiError("INVALID_STATE")
    defs = await service.custom_defs(db)
    valid = set(CORE_TARGETS) | {IMAGE_TARGET} | set(defs)
    mapping = {h: (body.mapping.get(h) or None) for h in meta.headers}
    targets = [t for t in mapping.values() if t]
    if any(t not in valid for t in targets):
        raise ApiError("NOT_FOUND")
    if len(targets) != len(set(targets)):
        raise ApiError("MAPPING_DUPLICATE_TARGET")
    if "part_number" not in targets or "part_name" not in targets:
        raise ApiError("MAPPING_INCOMPLETE")

    sig = signature(meta.headers)
    name = (body.save_as or "").strip() or Path(batch.file_name).stem
    saved = (await db.execute(select(ImportMapping).where(ImportMapping.header_signature == sig))).scalar_one_or_none()
    stored = {h: t for h, t in mapping.items() if t}
    if saved is None:
        saved = ImportMapping(name=name, header_signature=sig, mapping=stored, created_by=user.id)
        db.add(saved)
        await db.flush()
    else:
        saved.name = name
        saved.mapping = stored
    batch.mapping_id = saved.id
    batch.status = "validating"
    batch.progress_done = 0
    batch.progress_total = 0
    await db.commit()
    service.spawn(batch.id, service.validate(batch.id, mapping))
    return await batch_out(db, batch)


# ---------------------------------------------------------------- review
@router.get("/{batch_id}/rows", response_model=RowPage)
async def list_rows(batch_id: uuid.UUID, _: Admin, db: DB, action: Action | None = None,
                    limit: Annotated[int, Query(ge=1, le=200)] = 50, cursor: str | None = None) -> RowPage:
    await open_batch(db, batch_id)
    q = select(ImportRow).where(ImportRow.batch_id == batch_id)
    if action:
        q = q.where(ImportRow.action == action)
    if cursor:
        try:
            q = q.where(ImportRow.id > int(cursor))
        except ValueError as exc:
            raise ApiError("NOT_FOUND") from exc
    rows = list((await db.execute(q.order_by(ImportRow.id).limit(limit + 1))).scalars())
    more = len(rows) > limit
    rows = rows[:limit]
    return RowPage(items=[row_out(r) for r in rows], next_cursor=str(rows[-1].id) if more and rows else None)


@router.patch("/{batch_id}/rows/{row_id}", response_model=RowOut)
async def patch_row(batch_id: uuid.UUID, row_id: int, body: RowPatch, _: Admin, db: DB) -> RowOut:
    batch = await open_batch(db, batch_id, lock=True)
    if batch.status != "staged":
        raise ApiError("INVALID_STATE")
    row = await db.get(ImportRow, row_id, with_for_update=True)
    if row is None or row.batch_id != batch.id:
        raise ApiError("NOT_FOUND")

    if body.data is not None:
        if row.action == "missing" or row.source_row is None:
            raise ApiError("INVALID_STATE")
        saved = await db.get(ImportMapping, batch.mapping_id) if batch.mapping_id else None
        targets = list(dict.fromkeys(saved.mapping.values())) if saved else []
        ctx = await service.load_context(db, targets)
        old_norm = normalize_part_number(str(row.data.get("part_number", ""))) if row.data.get("part_number") else None
        merged = dict(row.data)
        for k, v in body.data.items():
            if k in targets and k != IMAGE_TARGET:  # the picture comes from the file; it can't be typed in
                merged[k] = v
        # Re-check this row and every row whose part number it shared before or shares now (duplicates).
        others = list((await db.execute(select(ImportRow).where(ImportRow.batch_id == batch.id,
                                                                ImportRow.source_row.is_not(None),
                                                                ImportRow.id != row.id))).scalars())
        cleaned_self = clean(row.source_row, merged, ctx)
        cleaned_others = {o.id: clean(o.source_row or 0, o.data, ctx) for o in others}
        dups = duplicate_rows([cleaned_self, *cleaned_others.values()])
        affected = {old_norm, cleaned_self.number_norm} - {None}
        for target_row, c in [(row, cleaned_self), *[(o, cleaned_others[o.id]) for o in others]]:
            if target_row is not row and c.number_norm not in affected:
                continue
            result = classify(c, ctx, dups)
            target_row.action = result.action
            target_row.part_id = result.part_id
            target_row.data = result.data
            target_row.diff = result.diff
            target_row.errors = result.errors
            target_row.accepted = result.accepted
    if body.accepted is not None:
        if row.action not in ("new", "update", "missing"):
            raise ApiError("INVALID_STATE")
        row.accepted = body.accepted
    await db.flush()
    await service.recount(db, batch.id)
    await db.commit()
    await db.refresh(row)
    return row_out(row)


# ---------------------------------------------------------------- commit / discard
@router.post("/{batch_id}/commit", response_model=CommitOut)
async def commit_import(batch_id: uuid.UUID, user: Admin, db: DB) -> CommitOut:
    batch = await open_batch(db, batch_id, lock=True)
    if batch.status != "staged":
        raise ApiError("INVALID_STATE")
    await service.lock_parts_table(db)
    saved = await db.get(ImportMapping, batch.mapping_id) if batch.mapping_id else None
    targets = list(dict.fromkeys(saved.mapping.values())) if saved else []
    ctx = await service.load_context(db, targets)
    rows = list((await db.execute(select(ImportRow).where(ImportRow.batch_id == batch.id,
                                                          ImportRow.accepted.is_(True),
                                                          ImportRow.action.in_(("new", "update", "missing")))
                                  .order_by(ImportRow.id))).scalars())
    now = now_utc()
    new_rows: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    missing: list[uuid.UUID] = []
    for r in rows:
        if r.action == "missing":
            missing.append(r.part_id)  # type: ignore[arg-type]
            continue
        norm = normalize_part_number(str(r.data["part_number"]))
        existing = ctx.parts.get(norm)
        if r.action == "new":
            if existing is not None:
                raise ApiError("STALE_WRITE")
            custom = {k: v for k, v in r.data.items() if k in ctx.defs}
            new_rows.append({"part_number": r.data["part_number"], "part_name": r.data["part_name"],
                             "description": r.data.get("description"), "revision": r.data.get("revision"),
                             "custom_data": custom, "status": "active", "source": "import",
                             "last_import_batch_id": batch.id, "created_by": user.id, "updated_by": user.id,
                             "image_asset_id": _image_id(r.data)})
        else:
            if existing is None or existing.id != r.part_id:
                raise ApiError("STALE_WRITE")
            cur = existing.values
            custom = {k: v for k, v in cur.items() if k not in CORE_KEYS}
            custom.update({k: v for k, v in r.data.items() if k in ctx.defs})  # mapped keys overwrite; others kept
            updates.append({"b_id": existing.id, "b_name": r.data.get("part_name", cur.get("part_name")),
                            "b_desc": r.data.get("description", cur.get("description")),
                            "b_rev": r.data.get("revision", cur.get("revision")), "b_custom": custom,
                            "b_status": "active" if r.diff and "status" in r.diff else existing.status,
                            "b_image": _image_id(r.data)})
    try:
        # COPY instead of row-by-row INSERT/UPDATE: a 50,000-row commit stays a few seconds (row triggers still fire).
        await service.copy_records(db, "part", NEW_PART_COLUMNS, [
            (r["part_number"], r["part_name"], r["description"], r["revision"], json.dumps(r["custom_data"]), "active",
             "import", batch.id, user.id, user.id, r["image_asset_id"]) for r in new_rows])
        if updates:
            await db.execute(text("CREATE TEMP TABLE import_update (id uuid PRIMARY KEY, part_name text, "
                                  "description text, revision text, custom_data jsonb, status text, image_asset_id uuid) "
                                  "ON COMMIT DROP"))
            await service.copy_records(db, "import_update", ["id", "part_name", "description", "revision", "custom_data",
                                                              "status", "image_asset_id"],
                                       [(u["b_id"], u["b_name"], u["b_desc"], u["b_rev"], json.dumps(u["b_custom"]),
                                         u["b_status"], u["b_image"]) for u in updates])
            await db.execute(text(
                "UPDATE part p SET part_name = u.part_name, description = u.description, revision = u.revision, "
                "custom_data = u.custom_data, status = u.status, source = 'import', last_import_batch_id = :b, "
                "image_asset_id = coalesce(u.image_asset_id, p.image_asset_id), "
                "updated_by = :u FROM import_update u WHERE p.id = u.id"), {"b": batch.id, "u": user.id})
        if missing:
            await db.execute(update(Part).where(Part.id.in_(missing), Part.status == "active")
                             .values(status="inactive", updated_by=user.id))
    except (IntegrityError, DBAPIError, asyncpg.PostgresError) as exc:  # COPY raises asyncpg's own errors
        await db.rollback()
        raise ApiError("STALE_WRITE") from exc

    skipped = batch.invalid_count
    batch.new_count, batch.updated_count, batch.missing_count = len(new_rows), len(updates), len(missing)
    batch.status = "committed"
    batch.committed_at = now
    audit(db, user.id, "import.commit", "import_batch", batch.id, None,
          {"file_name": batch.file_name, "new": len(new_rows), "updated": len(updates),
           "marked_inactive": len(missing), "skipped": skipped})
    await db.commit()
    service.remove_file(batch)
    return CommitOut(new=len(new_rows), updated=len(updates), marked_inactive=len(missing), skipped=skipped,
                     batch=await batch_out(db, batch))


@router.post("/{batch_id}/discard", response_model=BatchOut)
async def discard_import(batch_id: uuid.UUID, _: Admin, db: DB) -> BatchOut:
    batch = await open_batch(db, batch_id, lock=True)
    if batch.status == "committed":
        raise ApiError("INVALID_STATE")
    batch.status = "discarded"
    await db.commit()
    service.remove_file(batch)
    return await batch_out(db, batch)
