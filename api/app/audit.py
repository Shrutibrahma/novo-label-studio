"""Audit rows (spec section 5, invariant 1). Always written inside the caller's transaction."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [jsonable(v) for v in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


def audit(db: AsyncSession, actor_id: uuid.UUID | None, action: str, entity: str, entity_id: Any,
          before: Any = None, after: Any = None) -> None:
    db.add(AuditLog(actor_id=actor_id, action=action, entity=entity, entity_id=str(entity_id),
                    before=jsonable(before), after=jsonable(after)))
