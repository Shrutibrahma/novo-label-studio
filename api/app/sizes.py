"""Label sizes: GET/POST /sizes, PATCH /sizes/{id} (section 6; rules in section 3)."""

from __future__ import annotations

import uuid
from decimal import ROUND_DOWN, Decimal
from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.audit import audit
from app.auth.deps import DB, Admin, AnyUser
from app.errors import ApiError, field_error
from app.models import LabelConfig, LabelSize, PrintedLabel

router = APIRouter(prefix="/sizes", tags=["sizes"])

MIN_WIDTH, MAX_WIDTH = Decimal("2.00"), Decimal("4.40")
MIN_HEIGHT, MAX_HEIGHT = Decimal("0.50"), Decimal("11.00")
STEP = Decimal("0.01")


class SizeOut(BaseModel):
    id: str
    name: str
    width_in: float
    height_in: float
    active: bool
    used_by: int = 0


class SizeIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    width_in: Decimal
    height_in: Decimal


class SizePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    width_in: Decimal | None = None
    height_in: Decimal | None = None
    active: bool | None = None


def size_out(s: LabelSize, used_by: int = 0) -> SizeOut:
    return SizeOut(id=str(s.id), name=s.name, width_in=float(s.width_in), height_in=float(s.height_in),
                   active=s.active, used_by=used_by)


def validate_dimensions(width: Decimal, height: Decimal) -> tuple[Decimal, Decimal]:
    if width.quantize(STEP, ROUND_DOWN) != width or not (MIN_WIDTH <= width <= MAX_WIDTH):
        raise ApiError("SIZE_UNSUPPORTED", fields={"width_in": "This size doesn't fit the ZQ630 Plus "
                                                   "(media 2.0–4.4 in wide)."})
    if height.quantize(STEP, ROUND_DOWN) != height or not (MIN_HEIGHT <= height <= MAX_HEIGHT):
        raise field_error("FIELD_OUT_OF_RANGE", "height_in", "Height", min="0.50", max="11.00")
    return width, height


async def labels_using(db: DB, size_id: uuid.UUID) -> int:
    return int((await db.execute(
        select(func.count()).select_from(PrintedLabel)
        .join(LabelConfig, LabelConfig.id == PrintedLabel.label_config_id)
        .where(LabelConfig.label_size_id == size_id)
    )).scalar_one())


async def usage_counts(db: DB) -> dict[uuid.UUID, int]:
    rows = (await db.execute(
        select(LabelConfig.label_size_id, func.count(PrintedLabel.id))
        .join(PrintedLabel, PrintedLabel.label_config_id == LabelConfig.id)
        .group_by(LabelConfig.label_size_id)
    )).all()
    return {r[0]: int(r[1]) for r in rows}


@router.get("", response_model=list[SizeOut])
async def list_sizes(_: AnyUser, db: DB) -> list[SizeOut]:
    sizes = (await db.execute(select(LabelSize).order_by(LabelSize.width_in, LabelSize.height_in,
                                                          LabelSize.name))).scalars().all()
    used = await usage_counts(db)
    return [size_out(s, used.get(s.id, 0)) for s in sizes]


async def _name_taken(db: DB, name: str, exclude: uuid.UUID | None = None) -> bool:
    q = select(LabelSize.id).where(func.lower(LabelSize.name) == name.lower())
    if exclude:
        q = q.where(LabelSize.id != exclude)
    return (await db.execute(q)).first() is not None


@router.post("", response_model=SizeOut, status_code=201)
async def create_size(body: SizeIn, user: Admin, db: DB) -> SizeOut:
    width, height = validate_dimensions(body.width_in, body.height_in)
    name = body.name.strip()
    if await _name_taken(db, name):
        raise ApiError("SIZE_NAME_TAKEN", fields={"name": "A size with this name already exists."})
    size = LabelSize(name=name, width_in=width, height_in=height)
    db.add(size)
    await db.flush()
    audit(db, user.id, "size.create", "label_size", size.id, None,
          {"name": name, "width_in": width, "height_in": height})
    await db.commit()
    return size_out(size)


@router.patch("/{size_id}", response_model=SizeOut)
async def update_size(size_id: uuid.UUID, body: SizePatch, user: Admin, db: DB) -> SizeOut:
    size = await db.get(LabelSize, size_id, with_for_update=True)
    if size is None:
        raise ApiError("NOT_FOUND")
    before = {"name": size.name, "width_in": size.width_in, "height_in": size.height_in, "active": size.active}
    if body.width_in is not None or body.height_in is not None:
        width = body.width_in if body.width_in is not None else size.width_in
        height = body.height_in if body.height_in is not None else size.height_in
        if width != size.width_in or height != size.height_in:
            n = await labels_using(db, size.id)
            if n:
                raise ApiError("SIZE_IN_USE", n=n)
            size.width_in, size.height_in = validate_dimensions(width, height)
    if body.name is not None and body.name.strip() != size.name:
        if await _name_taken(db, body.name.strip(), exclude=size.id):
            raise ApiError("SIZE_NAME_TAKEN", fields={"name": "A size with this name already exists."})
        size.name = body.name.strip()
    if body.active is not None:
        size.active = body.active
    after = {"name": size.name, "width_in": size.width_in, "height_in": size.height_in, "active": size.active}
    if after != before:
        audit(db, user.id, "size.update", "label_size", size.id, before, after)
    await db.commit()
    return size_out(size, await labels_using(db, size.id))
