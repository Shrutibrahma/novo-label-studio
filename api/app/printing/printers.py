"""GET/PATCH /printers, /printers/{id}; POST /printers/{id}/agent-token (section 6, screen 12.13)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from app.audit import audit
from app.auth.deps import DB, Admin, AnyUser
from app.concurrency import check_if_match
from app.errors import ApiError, field_error
from app.models import LabelSize, Printer, PrintAgent
from app.printing.agent_auth import issue_token
from app.printing.status import effective_status
from app.sizes import SizeOut, size_out

router = APIRouter(prefix="/printers", tags=["printers"])


class PrinterOut(BaseModel):
    id: str
    name: str
    model: str
    dpi: int
    print_method: str
    print_width_in: float
    status: str
    reported_status: str
    last_status_at: datetime | None
    agent_last_seen_at: datetime | None
    loaded_label_size: SizeOut | None
    offset_x_dots: int
    offset_y_dots: int
    darkness: int | None
    speed_ips: float | None
    is_default: bool
    updated_at: datetime


class PrinterPatch(BaseModel):
    loaded_label_size_id: uuid.UUID | None = None
    clear_loaded_label_size: bool = False
    darkness: int | None = Field(default=None, ge=0, le=30)
    clear_darkness: bool = False
    speed_ips: int | None = Field(default=None, ge=1, le=14)
    clear_speed: bool = False
    offset_x_dots: int | None = Field(default=None, ge=-200, le=200)
    offset_y_dots: int | None = Field(default=None, ge=-200, le=200)
    is_default: bool | None = None


class TokenOut(BaseModel):
    agent_token: str


async def printer_out(db: DB, p: Printer) -> PrinterOut:
    agent = await db.get(PrintAgent, p.agent_id)
    size = await db.get(LabelSize, p.loaded_label_size_id) if p.loaded_label_size_id else None
    last_seen = agent.last_seen_at if agent else None
    return PrinterOut(
        id=str(p.id), name=p.name, model=p.model, dpi=p.dpi, print_method=p.print_method,
        print_width_in=float(p.print_width_in), status=effective_status(p.last_status, last_seen),
        reported_status=p.last_status, last_status_at=p.last_status_at, agent_last_seen_at=last_seen,
        loaded_label_size=size_out(size) if size else None, offset_x_dots=p.offset_x_dots,
        offset_y_dots=p.offset_y_dots, darkness=p.darkness,
        speed_ips=float(p.speed_ips) if p.speed_ips is not None else None, is_default=p.is_default,
        updated_at=p.updated_at,
    )


async def default_printer(db: DB) -> Printer:
    p = (await db.execute(select(Printer).where(Printer.is_default.is_(True)))).scalar_one_or_none()
    if p is None:
        raise ApiError("NOT_FOUND")
    return p


def snapshot(p: Printer) -> dict[str, object]:
    return {"loaded_label_size_id": p.loaded_label_size_id, "darkness": p.darkness, "speed_ips": p.speed_ips,
            "offset_x_dots": p.offset_x_dots, "offset_y_dots": p.offset_y_dots, "is_default": p.is_default}


@router.get("", response_model=list[PrinterOut])
async def list_printers(_: AnyUser, db: DB) -> list[PrinterOut]:
    printers = (await db.execute(select(Printer).order_by(Printer.is_default.desc(), Printer.name))).scalars()
    return [await printer_out(db, p) for p in printers]


@router.get("/{printer_id}", response_model=PrinterOut)
async def get_printer(printer_id: uuid.UUID, _: AnyUser, db: DB) -> PrinterOut:
    p = await db.get(Printer, printer_id)
    if p is None:
        raise ApiError("NOT_FOUND")
    return await printer_out(db, p)


@router.patch("/{printer_id}", response_model=PrinterOut)
async def patch_printer(printer_id: uuid.UUID, body: PrinterPatch, user: Admin, db: DB,
                        if_match: Annotated[str | None, Header()] = None) -> PrinterOut:
    p = await db.get(Printer, printer_id, with_for_update=True)
    if p is None:
        raise ApiError("NOT_FOUND")
    check_if_match(if_match, p.updated_at)
    before = snapshot(p)
    if body.clear_loaded_label_size:
        p.loaded_label_size_id = None
    elif body.loaded_label_size_id is not None:
        size = await db.get(LabelSize, body.loaded_label_size_id)
        if size is None or not size.active:
            raise field_error("FIELD_REQUIRED", "loaded_label_size_id", "Loaded labels")
        p.loaded_label_size_id = size.id
    if body.clear_darkness:
        p.darkness = None
    elif body.darkness is not None:
        p.darkness = body.darkness
    if body.clear_speed:
        p.speed_ips = None
    elif body.speed_ips is not None:
        p.speed_ips = Decimal(body.speed_ips)
    if body.offset_x_dots is not None:
        p.offset_x_dots = body.offset_x_dots
    if body.offset_y_dots is not None:
        p.offset_y_dots = body.offset_y_dots
    if body.is_default is True and not p.is_default:
        await db.execute(update(Printer).where(Printer.id != p.id).values(is_default=False))
        await db.flush()
        p.is_default = True
    after = snapshot(p)
    if after != before:
        audit(db, user.id, "printer.update", "printer", p.id, before, after)
    await db.commit()
    await db.refresh(p)
    return await printer_out(db, p)


@router.post("/{printer_id}/agent-token", response_model=TokenOut)
async def new_agent_token(printer_id: uuid.UUID, user: Admin, db: DB) -> TokenOut:
    p = await db.get(Printer, printer_id)
    if p is None:
        raise ApiError("NOT_FOUND")
    agent = await db.get(PrintAgent, p.agent_id, with_for_update=True)
    if agent is None:
        raise ApiError("NOT_FOUND")
    token, token_hash = issue_token()
    agent.token_hash = token_hash
    audit(db, user.id, "printer.update", "printer", p.id, {"agent_token": "rotated"}, {"agent_token": "issued"})
    await db.commit()
    return TokenOut(agent_token=token)
