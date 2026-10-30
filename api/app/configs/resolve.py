"""Which label type a part prints as (v1.1 D11 amended). One order, used by part detail and lists, preview and
print; the client never re-implements it:

1. the part's preferred type, if set and not archived      -> "preferred"
2. else the type of the part's most recent print (not a reprint), if not archived -> "last_printed"
3. else the browser's "Print as" choice                      -> "print_as"
4. else the first type                                       -> "first"
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.effective import resolve_type
from app.models import LabelType

Reason = Literal["preferred", "last_printed", "print_as", "first"]

_RESOLVE = text("""
SELECT p.id AS part_id, pt.id AS preferred_id, lt.id AS last_id
  FROM part p
  LEFT JOIN label_type pt ON pt.id = p.preferred_label_type_id AND NOT pt.archived
  LEFT JOIN LATERAL (
        SELECT c.label_type_id
          FROM printed_label pl
          JOIN label_config c ON c.id = pl.label_config_id
         WHERE pl.part_id = p.id AND pl.reprint_of IS NULL
         ORDER BY pl.created_at DESC, pl.id DESC
         LIMIT 1) lp ON true
  LEFT JOIN label_type lt ON lt.id = lp.label_type_id AND NOT lt.archived
 WHERE p.id = ANY(:ids)
""")


@dataclass(frozen=True)
class Resolved:
    type: LabelType
    reason: Reason


async def resolve_many(db: AsyncSession, part_ids: list[uuid.UUID], browser_choice_id: uuid.UUID | None
                       ) -> dict[uuid.UUID, Resolved]:
    if not part_ids:
        return {}
    rows = (await db.execute(_RESOLVE, {"ids": part_ids})).all()
    fallback: Resolved | None = None
    if browser_choice_id is not None:
        chosen = await db.get(LabelType, browser_choice_id)
        if chosen is not None and not chosen.archived:
            fallback = Resolved(chosen, "print_as")
    out: dict[uuid.UUID, Resolved] = {}
    for r in rows:
        if r.preferred_id is not None:
            out[r.part_id] = Resolved(await _type(db, r.preferred_id), "preferred")
        elif r.last_id is not None:
            out[r.part_id] = Resolved(await _type(db, r.last_id), "last_printed")
        else:
            if fallback is None:
                fallback = Resolved(await resolve_type(db, None), "first")
            out[r.part_id] = fallback
    return out


async def _type(db: AsyncSession, type_id: uuid.UUID) -> LabelType:
    t = await db.get(LabelType, type_id)
    assert t is not None
    return t


async def resolve_label_type(db: AsyncSession, part_id: uuid.UUID, browser_choice_id: uuid.UUID | None
                             ) -> tuple[LabelType, Reason]:
    r = (await resolve_many(db, [part_id], browser_choice_id))[part_id]
    return r.type, r.reason
