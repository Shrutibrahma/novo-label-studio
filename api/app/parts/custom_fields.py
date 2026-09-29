"""GET/POST /custom-fields, PATCH /custom-fields/{key} (section 6). The type is immutable."""

from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import audit
from app.auth.deps import DB, Admin, AnyUser
from app.errors import ApiError, field_error
from app.models import CustomFieldDef
from app.parts.values import RESERVED_KEYS, FieldDef, key_from_label

router = APIRouter(prefix="/custom-fields", tags=["custom-fields"])

KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
MAX_CHOICES = 100


class CustomFieldOut(BaseModel):
    key: str
    label: str
    data_type: str
    choices: list[str] | None
    required: bool
    searchable: bool
    printable: bool
    sort_order: int


class CustomFieldIn(BaseModel):
    key: str | None = Field(default=None, max_length=63)
    label: str = Field(min_length=1, max_length=80)
    data_type: Literal["text", "number", "date", "choice"]
    choices: list[str] | None = None
    required: bool = False
    searchable: bool = False
    printable: bool = True
    sort_order: int | None = None


class CustomFieldPatch(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=80)
    choices: list[str] | None = None
    required: bool | None = None
    searchable: bool | None = None
    printable: bool | None = None
    sort_order: int | None = None


def out(f: CustomFieldDef) -> CustomFieldOut:
    return CustomFieldOut(key=f.key, label=f.label, data_type=f.data_type, choices=f.choices, required=f.required,
                          searchable=f.searchable, printable=f.printable, sort_order=f.sort_order)


def as_def(f: CustomFieldDef) -> FieldDef:
    return FieldDef(key=f.key, label=f.label, data_type=f.data_type, choices=tuple(f.choices or ()),
                    required=f.required)


async def all_fields(db: AsyncSession) -> list[CustomFieldDef]:
    return list((await db.execute(select(CustomFieldDef).order_by(CustomFieldDef.sort_order,
                                                                  CustomFieldDef.label))).scalars())


def clean_choices(choices: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for c in choices or []:
        t = c.strip()
        if t and t.lower() not in seen:
            cleaned.append(t)
            seen.add(t.lower())
    if not cleaned:
        raise field_error("FIELD_REQUIRED", "choices", "Choices")
    if len(cleaned) > MAX_CHOICES:
        raise field_error("FIELD_OUT_OF_RANGE", "choices", "Choices", min=1, max=MAX_CHOICES)
    return cleaned


@router.get("", response_model=list[CustomFieldOut])
async def list_fields(_: AnyUser, db: DB) -> list[CustomFieldOut]:
    return [out(f) for f in await all_fields(db)]


@router.post("", response_model=CustomFieldOut, status_code=201)
async def create_field(body: CustomFieldIn, user: Admin, db: DB) -> CustomFieldOut:
    key = (body.key or key_from_label(body.label)).strip()
    if not KEY_RE.match(key):
        raise ApiError("FIELD_KEY_INVALID", fields={"key": "Key can use lowercase letters, numbers and "
                                                   "underscores, starting with a letter."})
    if key in RESERVED_KEYS or await db.get(CustomFieldDef, key) is not None:
        raise ApiError("FIELD_KEY_TAKEN", fields={"key": "A field with this key already exists."})
    choices = clean_choices(body.choices) if body.data_type == "choice" else None
    sort_order = body.sort_order
    if sort_order is None:
        sort_order = int((await db.execute(select(func.coalesce(func.max(CustomFieldDef.sort_order), -1) + 1)))
                         .scalar_one())
    f = CustomFieldDef(key=key, label=body.label.strip(), data_type=body.data_type, choices=choices,
                       required=body.required, searchable=body.searchable, printable=body.printable,
                       sort_order=sort_order)
    db.add(f)
    await db.flush()
    audit(db, user.id, "field.create", "custom_field_def", key, None, out(f).model_dump())
    await db.commit()
    return out(f)


@router.patch("/{key}", response_model=CustomFieldOut)
async def update_field(key: str, body: CustomFieldPatch, user: Admin, db: DB) -> CustomFieldOut:
    f = await db.get(CustomFieldDef, key, with_for_update=True)
    if f is None:
        raise ApiError("NOT_FOUND")
    before = out(f).model_dump()
    if body.label is not None:
        f.label = body.label.strip()
    if body.choices is not None:
        if f.data_type != "choice":
            raise field_error("FIELD_REQUIRED", "choices", "Choices")
        f.choices = clean_choices(body.choices)
    for attr in ("required", "searchable", "printable", "sort_order"):
        value = getattr(body, attr)
        if value is not None:
            setattr(f, attr, value)
    after = out(f).model_dump()
    if after != before:
        audit(db, user.id, "field.update", "custom_field_def", key, before, after)
    await db.commit()
    return out(f)
