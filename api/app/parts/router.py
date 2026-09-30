"""Parts master: list/search, detail, create, update, archive/restore, images (section 6; screens 12.4, 12.7–12.9)."""

from __future__ import annotations

import base64
import io
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Header, Query, UploadFile
from fastapi.responses import Response
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import audit
from app.auth.deps import DB, Admin, AnyUser
from app.concurrency import check_if_match
from app.config import get_settings
from app.configs.effective import effective_config
from app.errors import ApiError
from app.models import AppUser, Asset, LabelConfig, LabelSize, Part, PartAlias
from app.parts.custom_fields import all_fields, as_def
from app.parts.values import (
    FieldDef,
    ValueError_,
    check_core,
    is_blank,
    normalize_part_number,
    parse_custom,
)
from app.render.canvas import sha256

router = APIRouter(tags=["parts"])

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_EDGE = 1024
IMAGE_TYPES = {"image/png": {".png"}, "image/jpeg": {".jpg", ".jpeg"}, "image/webp": {".webp"}}
PIL_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}

Status = Literal["active", "inactive", "archived", "all"]
LabelStateFilter = Literal["current", "out_of_date", "never_printed"]


# ---------------------------------------------------------------- response models
class SizeBrief(BaseModel):
    id: str
    name: str
    width_in: float
    height_in: float


class PartListItem(BaseModel):
    id: str
    part_number: str
    part_name: str
    description: str | None
    revision: str | None
    status: str
    label_name: str | None
    has_image: bool
    image_version: str | None
    label_state: str
    last_printed_at: datetime | None
    size: SizeBrief | None
    config_version: int | None
    has_override: bool
    updated_at: datetime
    score: float | None = None
    matched_on: str | None = None


class PartList(BaseModel):
    items: list[PartListItem]
    next_cursor: str | None


class AliasOut(BaseModel):
    id: str
    alias: str
    is_label_name: bool
    created_at: datetime


class ConfigBrief(BaseModel):
    id: str
    version: int
    scope: str
    size: SizeBrief
    qr_mode: str
    serial_mode: str
    spec: dict[str, Any]
    created_at: datetime
    created_by_name: str


class PartDetail(BaseModel):
    id: str
    part_number: str
    part_name: str
    description: str | None
    revision: str | None
    custom_data: dict[str, Any]
    status: str
    source: str
    label_name: str | None
    has_image: bool
    image_version: str | None
    aliases: list[AliasOut]
    config: ConfigBrief
    has_override: bool
    label_state: str
    last_printed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PartCreate(BaseModel):
    part_number: str = Field(max_length=200)
    part_name: str = Field(max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    revision: str | None = Field(default=None, max_length=200)
    label_name: str | None = Field(default=None, max_length=500)
    custom_data: dict[str, Any] = Field(default_factory=dict)


class PartPatch(BaseModel):
    part_number: str | None = Field(default=None, max_length=200)
    part_name: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    revision: str | None = Field(default=None, max_length=200)
    clear: list[Literal["description", "revision"]] = Field(default_factory=list)
    custom_data: dict[str, Any] | None = None


# ---------------------------------------------------------------- list / search
_SELECT = """
SELECT p.id, p.part_number, p.part_number_norm, p.part_name, p.description, p.revision, p.status,
       p.image_asset_id, p.updated_at,
       ln.alias AS label_name,
       coalesce(f.label_state, 'never_printed') AS label_state, f.last_printed_at,
       ls.id AS size_id, ls.name AS size_name, ls.width_in, ls.height_in,
       (pc.id IS NOT NULL) AS has_override, coalesce(pc.version, dc.version) AS config_version
"""
_JOINS = """
LEFT JOIN part_alias ln ON ln.part_id = p.id AND ln.is_label_name
LEFT JOIN part_label_freshness f ON f.part_id = p.id
LEFT JOIN label_config pc ON pc.part_id = p.id AND pc.scope = 'part' AND pc.is_current
LEFT JOIN label_config dc ON dc.scope = 'default' AND dc.is_current
LEFT JOIN label_size ls ON ls.id = coalesce(pc.label_size_id, dc.label_size_id)
"""

# search_parts() only returns active parts. For the Parts screen's Inactive/Archived/All filters the same
# scoring (migration 0002: word similarity for names, capped at 0.85) runs without the status restriction.
_SEARCH_ANY_STATUS = """
SELECT part_id, max(s) AS score FROM (
  SELECT p.id AS part_id,
         CASE WHEN p.part_number_norm = upper(btrim(:q)) THEN 1.0
              WHEN p.part_number_norm LIKE like_prefix(upper(btrim(:q))) THEN 0.9
              ELSE similarity(p.part_number_norm, upper(btrim(:q))) END::real AS s
    FROM part p
   WHERE p.part_number_norm % upper(btrim(:q)) OR p.part_number_norm LIKE like_prefix(upper(btrim(:q)))
  UNION ALL
  SELECT a.part_id,
         CASE WHEN a.alias_norm = normalize_alias(:q) THEN 1.0
              WHEN a.alias_norm LIKE like_prefix(normalize_alias(:q)) THEN 0.9
              ELSE similarity(a.alias_norm, normalize_alias(:q)) END::real
    FROM part_alias a
   WHERE a.alias_norm % normalize_alias(:q) OR a.alias_norm LIKE like_prefix(normalize_alias(:q))
  UNION ALL
  SELECT p.id, least(word_similarity(normalize_alias(:q), lower(p.part_name || ' ' || coalesce(p.description, ''))), 0.85)::real
    FROM part p
   WHERE normalize_alias(:q) <> '' AND normalize_alias(:q) <% lower(p.part_name || ' ' || coalesce(p.description, ''))
) h GROUP BY part_id
"""

# Searchable custom fields: exact (1.0) or prefix (0.9) match on the value, case-insensitive.
_CUSTOM_HITS = """
SELECT p.id AS part_id,
       CASE WHEN lower(btrim(p.custom_data ->> k)) = lower(btrim(:q)) THEN 1.0 ELSE 0.9 END::real AS score
  FROM part p CROSS JOIN unnest(CAST(:keys AS text[])) AS k
 WHERE lower(btrim(p.custom_data ->> k)) LIKE like_prefix(lower(btrim(:q)))
"""


def _encode_cursor(data: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> dict[str, Any] | None:
    if not cursor:
        return None
    try:
        return json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ApiError("NOT_FOUND") from exc


def _item(row: Any) -> PartListItem:
    size = (SizeBrief(id=str(row.size_id), name=row.size_name, width_in=float(row.width_in),
                      height_in=float(row.height_in)) if row.size_id else None)
    return PartListItem(
        id=str(row.id), part_number=row.part_number, part_name=row.part_name, description=row.description,
        revision=row.revision, status=row.status, label_name=row.label_name,
        has_image=row.image_asset_id is not None,
        image_version=str(row.image_asset_id) if row.image_asset_id else None,
        label_state=row.label_state, last_printed_at=row.last_printed_at, size=size,
        config_version=row.config_version, has_override=bool(row.has_override), updated_at=row.updated_at,
        score=getattr(row, "score", None), matched_on=None,
    )


def _filters(status: Status, label_state: LabelStateFilter | None, printed_within_days: int | None,
             params: dict[str, Any]) -> list[str]:
    where: list[str] = []
    if status != "all":
        where.append("p.status = :status")
        params["status"] = status
    if label_state:
        where.append("coalesce(f.label_state, 'never_printed') = :label_state")
        params["label_state"] = label_state
    if printed_within_days:
        where.append("f.last_printed_at >= now() - make_interval(days => :days)")
        params["days"] = printed_within_days
    return where


async def searchable_keys(db: AsyncSession) -> list[str]:
    return [f.key for f in await all_fields(db) if f.searchable]


@router.get("/parts", response_model=PartList)
async def list_parts(
    _: AnyUser,
    db: DB,
    q: Annotated[str | None, Query(max_length=200)] = None,
    status: Status = "active",
    label_state: LabelStateFilter | None = None,
    printed_within_days: Annotated[int | None, Query(ge=1, le=365)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> PartList:
    params: dict[str, Any] = {"lim": limit + 1}
    where = _filters(status, label_state, printed_within_days, params)
    query = (q or "").strip()
    if query:
        # Search results are ranked, so pagination is by offset within the ranked list.
        offset = int((_decode_cursor(cursor) or {}).get("o", 0))
        params.update(q=query, keys=await searchable_keys(db), off=offset)
        base_hits = ("SELECT part_id, score FROM search_parts(:q, 200)" if status == "active"
                     else _SEARCH_ANY_STATUS)
        sql = (f"WITH hits AS ({base_hits} UNION ALL {_CUSTOM_HITS}), "
               "best AS (SELECT part_id, max(score) AS score FROM hits GROUP BY part_id) "
               f"{_SELECT}, b.score FROM best b JOIN part p ON p.id = b.part_id {_JOINS} "
               f"{'WHERE ' + ' AND '.join(where) if where else ''} "
               "ORDER BY b.score DESC, p.part_number LIMIT :lim OFFSET :off")
        rows = (await db.execute(text(sql), params)).all()
        more = len(rows) > limit
        return PartList(items=[_item(r) for r in rows[:limit]],
                        next_cursor=_encode_cursor({"o": offset + limit}) if more else None)

    c = _decode_cursor(cursor)
    if c:
        where.append("(p.part_number_norm, p.id) > (:cn, CAST(:cid AS uuid))")
        params.update(cn=c["n"], cid=c["i"])
    sql = (f"{_SELECT} FROM part p {_JOINS} {'WHERE ' + ' AND '.join(where) if where else ''} "
           "ORDER BY p.part_number_norm, p.id LIMIT :lim")
    rows = (await db.execute(text(sql), params)).all()
    more = len(rows) > limit
    page = rows[:limit]
    nxt = _encode_cursor({"n": page[-1].part_number_norm, "i": str(page[-1].id)}) if more and page else None
    return PartList(items=[_item(r) for r in page], next_cursor=nxt)


# ---------------------------------------------------------------- detail
async def size_brief(db: AsyncSession, size_id: uuid.UUID) -> SizeBrief:
    s = await db.get(LabelSize, size_id)
    if s is None:
        raise ApiError("NOT_FOUND")
    return SizeBrief(id=str(s.id), name=s.name, width_in=float(s.width_in), height_in=float(s.height_in))


async def config_brief(db: AsyncSession, cfg: LabelConfig) -> ConfigBrief:
    author = await db.get(AppUser, cfg.created_by)
    return ConfigBrief(id=str(cfg.id), version=cfg.version, scope=cfg.scope, size=await size_brief(db, cfg.label_size_id),
                       qr_mode=cfg.qr_mode, serial_mode=cfg.serial_mode, spec=cfg.spec, created_at=cfg.created_at,
                       created_by_name=author.display_name if author else "")


async def aliases_of(db: AsyncSession, part_id: uuid.UUID) -> list[PartAlias]:
    return list((await db.execute(select(PartAlias).where(PartAlias.part_id == part_id)
                                  .order_by(PartAlias.is_label_name.desc(), PartAlias.created_at))).scalars())


def alias_out(a: PartAlias) -> AliasOut:
    return AliasOut(id=str(a.id), alias=a.alias, is_label_name=a.is_label_name, created_at=a.created_at)


async def get_part(db: AsyncSession, part_id: uuid.UUID, lock: bool = False) -> Part:
    part = await db.get(Part, part_id, with_for_update=lock)
    if part is None:
        raise ApiError("NOT_FOUND")
    return part


async def part_detail(db: AsyncSession, part: Part) -> PartDetail:
    aliases = await aliases_of(db, part.id)
    cfg = await effective_config(db, part.id)
    fresh = (await db.execute(text("SELECT label_state, last_printed_at FROM part_label_freshness "
                                   "WHERE part_id = :p"), {"p": part.id})).one()
    label = next((a.alias for a in aliases if a.is_label_name), None)
    return PartDetail(
        id=str(part.id), part_number=part.part_number, part_name=part.part_name, description=part.description,
        revision=part.revision, custom_data=part.custom_data, status=part.status, source=part.source,
        label_name=label, has_image=part.image_asset_id is not None,
        image_version=str(part.image_asset_id) if part.image_asset_id else None,
        aliases=[alias_out(a) for a in aliases], config=await config_brief(db, cfg),
        has_override=cfg.scope == "part", label_state=fresh.label_state, last_printed_at=fresh.last_printed_at,
        created_at=part.created_at, updated_at=part.updated_at,
    )


@router.get("/parts/{part_id}", response_model=PartDetail)
async def read_part(part_id: uuid.UUID, _: AnyUser, db: DB) -> PartDetail:
    return await part_detail(db, await get_part(db, part_id))


# ---------------------------------------------------------------- create / update
def value_error(field: str, err: ValueError_) -> ApiError:
    return ApiError(err.code if err.code in ("FIELD_REQUIRED", "FIELD_TOO_LONG", "FIELD_NOT_NUMBER",
                                             "FIELD_NOT_CHOICE", "FIELD_NOT_DATE") else "FIELD_REQUIRED",
                    fields={field: _ui_message(err)})


def _ui_message(err: ValueError_) -> str:
    # Manual entry uses the 14.2 wording ("{Field} is required."), imports keep 10.3's ("... is missing.").
    return err.message.replace(" is missing.", " is required.")


def apply_custom(defs: dict[str, FieldDef], current: dict[str, Any], incoming: dict[str, Any],
                 is_new: bool) -> dict[str, Any]:
    result = dict(current)
    for key, raw in incoming.items():
        field = defs.get(key)
        if field is None:
            raise ApiError("NOT_FOUND", fields={f"custom_data.{key}": "We couldn't find that. It may have been archived."})
        if is_blank(raw):
            if field.required:
                raise ApiError("FIELD_REQUIRED", fields={f"custom_data.{key}": f"{field.label} is required."})
            result.pop(key, None)
            continue
        try:
            result[key] = parse_custom(field, raw)
        except ValueError_ as err:
            raise value_error(f"custom_data.{key}", err) from err
    if is_new:
        for field in defs.values():
            if field.required and is_blank(result.get(field.key)):
                raise ApiError("FIELD_REQUIRED", fields={f"custom_data.{field.key}": f"{field.label} is required."})
    return result


async def alias_owner_of_number(db: AsyncSession, part_number: str, exclude: uuid.UUID | None) -> str | None:
    """Part number of the part that already uses `part_number` as a label name/alias (trigger semantics)."""
    q = (select(Part.part_number).join(PartAlias, PartAlias.part_id == Part.id)
         .where(func.upper(func.btrim(PartAlias.alias)) == normalize_part_number(part_number)))
    if exclude:
        q = q.where(Part.id != exclude)
    return (await db.execute(q)).scalars().first()


async def assert_number_free(db: AsyncSession, part_number: str, exclude: uuid.UUID | None = None) -> None:
    q = select(Part.id).where(Part.part_number_norm == normalize_part_number(part_number))
    if exclude:
        q = q.where(Part.id != exclude)
    if (await db.execute(q)).first():
        raise ApiError("PART_NUMBER_TAKEN", fields={"part_number": "A part with this number already exists."})
    owner = await alias_owner_of_number(db, part_number, exclude)
    if owner:
        msg = f"This part number is already used as a label name for part {owner}."
        raise ApiError("PART_NUMBER_IS_ALIAS", fields={"part_number": msg}, part_number=owner)


def snapshot(p: Part) -> dict[str, Any]:
    return {"part_number": p.part_number, "part_name": p.part_name, "description": p.description,
            "revision": p.revision, "custom_data": p.custom_data, "status": p.status,
            "image_asset_id": p.image_asset_id}


def _check(key: str, value: Any, required: bool) -> str | None:
    try:
        return check_core(key, value, required)
    except ValueError_ as err:
        raise value_error(key, err) from err


async def _commit_part(db: AsyncSession) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if "part_number_norm_uq" in str(exc.orig):
            raise ApiError("PART_NUMBER_TAKEN", fields={"part_number": "A part with this number already exists."}) from exc
        raise
    except DBAPIError as exc:
        await db.rollback()
        if "already a label name" in str(exc.orig):
            # Lost a race with a concurrent alias insert; the pre-check normally reports the owner.
            raise ApiError("STALE_WRITE") from exc
        raise


@router.post("/parts", response_model=PartDetail, status_code=201)
async def create_part(body: PartCreate, user: Admin, db: DB) -> PartDetail:
    number = _check("part_number", body.part_number, True)
    name = _check("part_name", body.part_name, True)
    assert number is not None and name is not None
    description = _check("description", body.description, False)
    revision = _check("revision", body.revision, False)
    defs = {f.key: as_def(f) for f in await all_fields(db)}
    custom = apply_custom(defs, {}, body.custom_data, is_new=True)
    await assert_number_free(db, number)

    label_name = (body.label_name or "").strip()
    if label_name:
        from app.parts.aliases import validate_alias  # local import: aliases imports this module
        await validate_alias(db, label_name, part_id=None, new_part_number=number)

    part = Part(part_number=number, part_name=name, description=description, revision=revision, custom_data=custom,
                source="manual", created_by=user.id, updated_by=user.id)
    db.add(part)
    await db.flush()
    audit(db, user.id, "part.create", "part", part.id, None, snapshot(part))
    if label_name:
        alias = PartAlias(part_id=part.id, alias=label_name, is_label_name=True, created_by=user.id)
        db.add(alias)
        await db.flush()
        audit(db, user.id, "alias.create", "part_alias", alias.id, None,
              {"part_id": part.id, "alias": label_name, "is_label_name": True})
    await _commit_part(db)
    await db.refresh(part)
    return await part_detail(db, part)


@router.patch("/parts/{part_id}", response_model=PartDetail)
async def update_part(part_id: uuid.UUID, body: PartPatch, user: Admin, db: DB,
                      if_match: Annotated[str | None, Header()] = None) -> PartDetail:
    part = await get_part(db, part_id, lock=True)
    check_if_match(if_match, part.updated_at)
    before = snapshot(part)
    if body.part_number is not None:
        number = _check("part_number", body.part_number, True)
        assert number is not None
        if number != part.part_number:
            await assert_number_free(db, number, exclude=part.id)
            part.part_number = number
    if body.part_name is not None:
        name = _check("part_name", body.part_name, True)
        assert name is not None
        part.part_name = name
    if body.description is not None:
        part.description = _check("description", body.description, False)
    if body.revision is not None:
        part.revision = _check("revision", body.revision, False)
    for key in body.clear:
        setattr(part, key, None)
    if body.custom_data is not None:
        defs = {f.key: as_def(f) for f in await all_fields(db)}
        part.custom_data = apply_custom(defs, part.custom_data, body.custom_data, is_new=False)
    after = snapshot(part)
    if after != before:
        part.updated_by = user.id
        changed = [k for k in after if after[k] != before[k]]
        audit(db, user.id, "part.update", "part", part.id, {k: before[k] for k in changed},
              {k: after[k] for k in changed})
    await _commit_part(db)
    await db.refresh(part)
    return await part_detail(db, part)


async def _set_status(db: AsyncSession, user_id: uuid.UUID, part_id: uuid.UUID, status: str, action: str) -> Part:
    part = await get_part(db, part_id, lock=True)
    if part.status != status:
        audit(db, user_id, action, "part", part.id, {"status": part.status}, {"status": status})
        part.status = status
        part.updated_by = user_id
    await db.commit()
    await db.refresh(part)
    return part


@router.post("/parts/{part_id}/archive", response_model=PartDetail)
async def archive_part(part_id: uuid.UUID, user: Admin, db: DB) -> PartDetail:
    return await part_detail(db, await _set_status(db, user.id, part_id, "archived", "part.archive"))


@router.post("/parts/{part_id}/restore", response_model=PartDetail)
async def restore_part(part_id: uuid.UUID, user: Admin, db: DB) -> PartDetail:
    return await part_detail(db, await _set_status(db, user.id, part_id, "active", "part.update"))


# ---------------------------------------------------------------- images (manual upload)
def asset_path(storage_key: str) -> Path:
    return get_settings().asset_dir / storage_key


def reencode_image(data: bytes, declared_type: str | None, filename: str | None) -> bytes:
    """MIME + extension checked, decoded, re-encoded to PNG with the long edge ≤ 1024 px (section 15)."""
    ext = Path(filename or "").suffix.lower()
    allowed_ext = {e for exts in IMAGE_TYPES.values() for e in exts}
    if (declared_type or "") not in IMAGE_TYPES or ext not in allowed_ext:
        raise ApiError("IMAGE_UNSUPPORTED")
    if len(data) > MAX_IMAGE_BYTES:
        raise ApiError("IMAGE_TOO_LARGE")
    try:
        with Image.open(io.BytesIO(data)) as img:
            if PIL_FORMATS.get(img.format or "") is None or ext not in IMAGE_TYPES[PIL_FORMATS[img.format or ""]]:
                raise ApiError("IMAGE_UNSUPPORTED")
            img.load()
            converted = img.convert("RGBA") if img.mode not in ("RGB", "RGBA", "L", "LA") else img.copy()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ApiError("IMAGE_UNSUPPORTED") from exc
    converted.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    converted.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


@router.put("/parts/{part_id}/image", response_model=PartDetail)
async def upload_image(part_id: uuid.UUID, user: Admin, db: DB, file: Annotated[UploadFile, File()]) -> PartDetail:
    part = await get_part(db, part_id, lock=True)
    data = await file.read(MAX_IMAGE_BYTES + 1)
    png = reencode_image(data, file.content_type, file.filename)
    digest = sha256(png)
    asset = (await db.execute(select(Asset).where(Asset.sha256 == digest))).scalar_one_or_none()
    if asset is None:
        key = f"{digest.hex()[:2]}/{digest.hex()}.png"
        path = asset_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(png)
        tmp.replace(path)
        asset = Asset(sha256=digest, mime_type="image/png", byte_size=len(png), storage_key=key, created_by=user.id)
        db.add(asset)
        await db.flush()
    before = part.image_asset_id
    part.image_asset_id = asset.id
    part.updated_by = user.id
    audit(db, user.id, "part.update", "part", part.id, {"image_asset_id": before}, {"image_asset_id": asset.id})
    await db.commit()
    await db.refresh(part)
    return await part_detail(db, part)


@router.delete("/parts/{part_id}/image", response_model=PartDetail)
async def remove_image(part_id: uuid.UUID, user: Admin, db: DB) -> PartDetail:
    part = await get_part(db, part_id, lock=True)
    if part.image_asset_id is not None:
        audit(db, user.id, "part.update", "part", part.id, {"image_asset_id": part.image_asset_id},
              {"image_asset_id": None})
        part.image_asset_id = None
        part.updated_by = user.id
    await db.commit()
    await db.refresh(part)
    return await part_detail(db, part)


@router.get("/parts/{part_id}/image")
async def read_image(part_id: uuid.UUID, _: AnyUser, db: DB) -> Response:
    part = await get_part(db, part_id)
    asset = await db.get(Asset, part.image_asset_id) if part.image_asset_id else None
    if asset is None:
        raise ApiError("NOT_FOUND")
    path = asset_path(asset.storage_key)
    if not path.exists():
        raise ApiError("NOT_FOUND")
    return Response(path.read_bytes(), media_type=asset.mime_type,
                    headers={"Cache-Control": "private, max-age=31536000, immutable", "ETag": asset.sha256.hex()})
