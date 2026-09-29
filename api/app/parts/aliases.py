"""Label names and aliases (D10; section 6; screen 12.8 "Label names"; flow 13.4)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import audit
from app.auth.deps import DB, Admin, AnyUser
from app.errors import ApiError
from app.models import Part, PartAlias
from app.parts.router import AliasOut, alias_out, aliases_of, get_part
from app.parts.values import normalize_alias, normalize_part_number

router = APIRouter(tags=["aliases"])

MAX_ALIAS = 120


class AliasIn(BaseModel):
    alias: str = Field(max_length=500)
    is_label_name: bool = False


class AliasPatch(BaseModel):
    alias: str | None = Field(default=None, max_length=500)
    is_label_name: bool | None = None


async def validate_alias(db: AsyncSession, alias: str, part_id: uuid.UUID | None,
                         new_part_number: str | None = None, alias_id: uuid.UUID | None = None) -> str:
    text = alias.strip()
    norm = normalize_alias(text)
    if not norm:
        raise ApiError("ALIAS_EMPTY", fields={"alias": "Enter a name with at least one letter or number."})
    if len(text) > MAX_ALIAS:
        raise ApiError("FIELD_TOO_LONG", fields={"alias": f"Label name is longer than {MAX_ALIAS} characters."},
                       Field="Label name", max=MAX_ALIAS)
    q = select(Part.part_number, PartAlias.id).join(Part, Part.id == PartAlias.part_id).where(PartAlias.alias_norm == norm)
    if alias_id:
        q = q.where(PartAlias.id != alias_id)
    taken = (await db.execute(q)).first()
    if taken:
        raise ApiError("ALIAS_TAKEN", fields={"alias": f"This name is already used for part {taken[0]}."},
                       part_number=taken[0])
    pn = normalize_part_number(text)
    other = select(Part.id).where(Part.part_number_norm == pn)
    if part_id:
        other = other.where(Part.id != part_id)
    is_other_part = (await db.execute(other)).first() is not None
    if is_other_part and not (new_part_number and normalize_part_number(new_part_number) == pn):
        raise ApiError("ALIAS_IS_PART_NUMBER", fields={"alias": "This name is another part's part number."})
    return text


async def _commit(db: AsyncSession) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if "part_alias_norm_uq" in str(exc.orig) or "part_alias_label_name_uq" in str(exc.orig):
            raise ApiError("STALE_WRITE") from exc
        raise
    except DBAPIError as exc:
        await db.rollback()
        if "another part's part number" in str(exc.orig):
            raise ApiError("ALIAS_IS_PART_NUMBER", fields={"alias": "This name is another part's part number."}) from exc
        raise


async def _clear_label_name(db: AsyncSession, part_id: uuid.UUID, keep: uuid.UUID | None = None) -> None:
    q = update(PartAlias).where(PartAlias.part_id == part_id, PartAlias.is_label_name.is_(True))
    if keep:
        q = q.where(PartAlias.id != keep)
    await db.execute(q.values(is_label_name=False))
    await db.flush()


def _state(a: PartAlias) -> dict[str, object]:
    return {"part_id": a.part_id, "alias": a.alias, "is_label_name": a.is_label_name}


@router.get("/parts/{part_id}/aliases", response_model=list[AliasOut])
async def list_aliases(part_id: uuid.UUID, _: AnyUser, db: DB) -> list[AliasOut]:
    await get_part(db, part_id)
    return [alias_out(a) for a in await aliases_of(db, part_id)]


@router.post("/parts/{part_id}/aliases", response_model=AliasOut, status_code=201)
async def add_alias(part_id: uuid.UUID, body: AliasIn, user: Admin, db: DB) -> AliasOut:
    part = await get_part(db, part_id, lock=True)
    text = await validate_alias(db, body.alias, part.id)
    if body.is_label_name:
        await _clear_label_name(db, part.id)
    alias = PartAlias(part_id=part.id, alias=text, is_label_name=body.is_label_name, created_by=user.id)
    db.add(alias)
    await db.flush()
    audit(db, user.id, "alias.create", "part_alias", alias.id, None, _state(alias))
    await _commit(db)
    await db.refresh(alias)
    return alias_out(alias)


@router.patch("/aliases/{alias_id}", response_model=AliasOut)
async def update_alias(alias_id: uuid.UUID, body: AliasPatch, user: Admin, db: DB) -> AliasOut:
    alias = await db.get(PartAlias, alias_id, with_for_update=True)
    if alias is None:
        raise ApiError("NOT_FOUND")
    before = _state(alias)
    if body.alias is not None and body.alias.strip() != alias.alias:
        alias.alias = await validate_alias(db, body.alias, alias.part_id, alias_id=alias.id)
    if body.is_label_name is not None and body.is_label_name != alias.is_label_name:
        if body.is_label_name:
            await _clear_label_name(db, alias.part_id, keep=alias.id)
        alias.is_label_name = body.is_label_name
    after = _state(alias)
    if after != before:
        audit(db, user.id, "alias.update", "part_alias", alias.id, before, after)
    await _commit(db)
    await db.refresh(alias)
    return alias_out(alias)


@router.delete("/aliases/{alias_id}", status_code=204)
async def delete_alias(alias_id: uuid.UUID, user: Admin, db: DB) -> None:
    alias = await db.get(PartAlias, alias_id, with_for_update=True)
    if alias is None:
        raise ApiError("NOT_FOUND")
    audit(db, user.id, "alias.delete", "part_alias", alias.id, _state(alias), None)
    await db.delete(alias)
    await db.commit()
