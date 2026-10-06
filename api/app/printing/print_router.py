"""POST /print (section 6; flows 13.5–13.7; rules in 8.1, 8.3, 9.1–9.3, 14.1).

One user action = one print_request (owns the Idempotency-Key) that fans out into jobs of ≤ 200 labels.
Allocating serials, rendering, inserting printed_label rows and setting jobs to `rendered` happen in one
transaction (section 5 invariant 3); jobs move to `queued` right after it commits."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated, Any

from anyio import to_thread
from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import audit
from app.auth.deps import DB, AnyUser
from app.configs.effective import effective_config
from app.configs.spec import LabelSpec, ManualBox, parse_spec
from app.errors import ApiError
from app.models import LabelConfig, LabelGroup, LabelSize, Part, Printer, PrintedLabel, PrintJob, PrintRequest
from app.printing.jobs import JobOut, assert_printer_ready, job_out, printer_settings, queue_jobs
from app.render.canvas import sha256
from app.render.engine import RenderResult
from app.render.service import image_of, label_name_of, part_values, preview_serial, render_context, render_snapshot
from app.render.snapshot import build_snapshot, clean_manual, field_labels
from app.render.zpl import job_payload
from app.timeutil import local_today, request_zone

router = APIRouter(tags=["print"])

MAX_LABELS_PER_JOB = 200
MAX_LABELS_PER_REQUEST = 1000


class GroupIn(BaseModel):
    total: int = Field(ge=1, le=999)
    start_index: int = Field(ge=1, le=999)
    count: int | None = Field(default=None, ge=1, le=999)
    group_id: uuid.UUID | None = None


class ItemIn(BaseModel):
    part_id: uuid.UUID
    copies: int = Field(default=1, ge=1, le=50)
    quantity: int = Field(default=1, ge=1, le=200)
    manual_values: dict[str, Any] = Field(default_factory=dict)
    group: GroupIn | None = None


class PrintIn(BaseModel):
    printer_id: uuid.UUID | None = None
    items: list[ItemIn] = Field(min_length=1, max_length=200)
    # "I've loaded {size} labels" (12.6 step 6): confirms the loaded size and records it on the printer.
    loaded_size_confirmed: bool = False


class PrintOut(BaseModel):
    request_id: str
    jobs: list[JobOut]
    group_ids: list[str | None]
    serials: list[str]


@dataclass
class Planned:
    part: Part
    config: LabelConfig
    spec: LabelSpec
    size: LabelSize
    item: ItemIn
    manual: dict[str, Any]
    indexes: list[int | None]  # one entry per distinct label (box index, or None)
    group: LabelGroup | None = None


def parse_key(value: str | None) -> uuid.UUID:
    if not value:
        raise ApiError("IDEMPOTENCY_KEY_REQUIRED")
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ApiError("IDEMPOTENCY_KEY_REQUIRED") from exc


async def request_out(db: AsyncSession, req: PrintRequest) -> PrintOut:
    jobs = list((await db.execute(select(PrintJob).where(PrintJob.request_id == req.id)
                                  .order_by(PrintJob.seq_in_request))).scalars())
    outs = [await job_out(db, j) for j in jobs]
    serials = [lbl.serial_value for j in outs for lbl in j.labels if lbl.serial_value]
    group_ids = (req.request_body or {}).get("group_ids", [])
    return PrintOut(request_id=str(req.id), jobs=outs, group_ids=group_ids, serials=serials)


async def existing_request(db: AsyncSession, key: uuid.UUID) -> PrintRequest | None:
    return (await db.execute(select(PrintRequest).where(PrintRequest.idempotency_key == key))).scalar_one_or_none()


async def plan_items(db: AsyncSession, body: PrintIn, labels_for: dict[str, str]) -> list[Planned]:
    planned: list[Planned] = []
    for item in body.items:
        part = await db.get(Part, item.part_id)
        if part is None or part.status != "active":
            raise ApiError("NOT_FOUND")
        cfg = await effective_config(db, part.id)
        spec = parse_spec(cfg.spec)
        size = await db.get(LabelSize, cfg.label_size_id)
        assert size is not None
        box = spec.box_field()
        if item.group is not None:
            if box is None:
                raise ApiError("INVALID_STATE")
            g = item.group
            count = g.count if g.count is not None else g.total - g.start_index + 1
            if g.start_index + count - 1 > g.total:
                raise ApiError("FIELD_OUT_OF_RANGE", fields={"group.start_index": f"Box number must be between 1 and {g.total}."},
                               Field="Box number", min=1, max=g.total)
            indexes: list[int | None] = list(range(g.start_index, g.start_index + count))
        else:
            if cfg.serial_mode != "required" and item.quantity != 1:
                # Quantity is only offered with serials (9.2); without them only Copies exists.
                raise ApiError("FIELD_OUT_OF_RANGE", fields={"quantity": "Quantity must be between 1 and 1."},
                               Field="Quantity", min=1, max=1)
            indexes = [None] * item.quantity
        manual = clean_manual(spec, item.manual_values, field_labels(spec, labels_for))
        planned.append(Planned(part=part, config=cfg, spec=spec, size=size, item=item, manual=manual, indexes=indexes))
    total = sum(len(p.indexes) for p in planned)
    if total > MAX_LABELS_PER_REQUEST:
        raise ApiError("PRINT_TOO_LARGE", Field="Labels", min=1, max=MAX_LABELS_PER_REQUEST,
                       fields={"items": f"Labels must be between 1 and {MAX_LABELS_PER_REQUEST}."})
    return planned


async def check_loaded_size(db: AsyncSession, printer: Printer, planned: list[Planned], confirmed: bool,
                            user_id: uuid.UUID) -> None:
    """14.1: loaded size ≠ label size blocks printing until the operator confirms what is loaded."""
    sizes = {p.size.id: p.size for p in planned}
    mismatched = [s for sid, s in sizes.items() if sid != printer.loaded_label_size_id]
    if not mismatched:
        return
    if not confirmed:
        raise ApiError("SIZE_NOT_LOADED", size=mismatched[0].name)
    if len(sizes) > 1:
        # Only one size can be loaded: a batch mixing sizes can't all match after confirming one of them.
        raise ApiError("SIZE_NOT_LOADED", size=mismatched[-1].name)
    new_size = mismatched[0]
    audit(db, user_id, "printer.update", "printer", printer.id, {"loaded_label_size_id": printer.loaded_label_size_id},
          {"loaded_label_size_id": new_size.id})
    printer.loaded_label_size_id = new_size.id


def _first_warning(result: RenderResult) -> ApiError:
    w = result.warnings[0]
    err = ApiError(w.code if w.code in ("TEXT_TOO_LONG", "CONTENT_TOO_TALL", "QR_TOO_SMALL", "QR_PAYLOAD_TOO_LONG",
                                        "REQUIRED_VALUE_MISSING") else "CONTENT_TOO_TALL")
    err.message = w.message
    return err


@router.post("/print", response_model=PrintOut)
async def create_print(body: PrintIn, request: Request, user: AnyUser, db: DB,
                       idempotency_key: Annotated[str | None, Header()] = None) -> PrintOut:
    key = parse_key(idempotency_key)
    if (prior := await existing_request(db, key)) is not None:
        return await request_out(db, prior)

    # The printer row is only locked when this request records a newly loaded size on it.
    lock = body.loaded_size_confirmed
    if body.printer_id:
        printer = await db.get(Printer, body.printer_id, with_for_update=lock)
    else:
        q = select(Printer).where(Printer.is_default.is_(True))
        printer = (await db.execute(q.with_for_update() if lock else q)).scalar_one_or_none()
    if printer is None:
        raise ApiError("NOT_FOUND")
    await assert_printer_ready(db, printer)

    ctx = await render_context(db, printer)
    planned = await plan_items(db, body, ctx.custom_labels)
    await check_loaded_size(db, printer, planned, body.loaded_size_confirmed, user.id)
    print_date = local_today(request_zone(request)).isoformat()

    # Refuse before allocating anything if a label can't fit (the placeholder serial is the widest possible).
    for p in planned:
        values = part_values(p.part, await label_name_of(db, p.part.id), await image_of(db, p.part))
        labels = field_labels(p.spec, ctx.custom_labels)
        box = p.spec.box_field()
        manual = dict(p.manual)
        if box is not None:
            manual[box.key] = {"index": p.indexes[0] or 1, "total": p.item.group.total if p.item.group else 1}
        serial = preview_serial(ctx.sequence) if p.config.serial_mode == "required" else None
        snap = build_snapshot(p.spec, p.config.qr_mode, values, ctx.custom_keys, manual, serial, print_date, labels)
        result = await to_thread.run_sync(render_snapshot, snap, p.spec, p.config.qr_mode, p.size, printer, labels)
        if not result.fits:
            raise _first_warning(result)

    req = PrintRequest(idempotency_key=key, kind="print", request_body={}, created_by=user.id)
    db.add(req)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()  # a concurrent retry with the same key won the race: return its request
        prior = await existing_request(db, key)
        if prior is None:
            raise
        return await request_out(db, prior)

    rendered: list[tuple[Planned, int | None, str | None, dict[str, Any], RenderResult]] = []
    group_ids: list[str | None] = []
    for p in planned:
        n = len(p.indexes)
        serials: list[str | None] = [None] * n
        if p.config.serial_mode == "required":
            try:
                rows = await db.execute(text("SELECT allocate_serials(:s, :p, :n, :u)"),
                                        {"s": p.config.serial_sequence_id, "p": p.part.id, "n": n, "u": user.id})
            except DBAPIError as exc:
                if "exhausted" in str(exc.orig):
                    raise ApiError("SERIAL_EXHAUSTED") from exc
                raise
            serials = list(rows.scalars())
        box = p.spec.box_field()
        if p.item.group is not None and box is not None:
            p.group = await resolve_group(db, p, box, user.id)
        group_ids.append(str(p.group.id) if p.group else None)
        values = part_values(p.part, await label_name_of(db, p.part.id), await image_of(db, p.part))
        labels = field_labels(p.spec, ctx.custom_labels)
        for index, serial in zip(p.indexes, serials, strict=True):
            manual = dict(p.manual)
            if box is not None:
                manual[box.key] = {"index": index or 1, "total": p.item.group.total if p.item.group else 1}
            snap = build_snapshot(p.spec, p.config.qr_mode, values, ctx.custom_keys, manual, serial, print_date, labels)
            result = await to_thread.run_sync(render_snapshot, snap, p.spec, p.config.qr_mode, p.size, printer, labels)
            if not result.fits:  # can't happen after the placeholder check; never print a label that doesn't fit
                raise _first_warning(result)
            rendered.append((p, index, serial, snap, result))

    settings = printer_settings(printer)
    job_ids: list[uuid.UUID] = []
    for seq_in_request, start in enumerate(range(0, len(rendered), MAX_LABELS_PER_JOB), start=1):
        chunk = rendered[start:start + MAX_LABELS_PER_JOB]
        payload = await to_thread.run_sync(job_payload, [(r.png, p.item.copies) for p, _, _, _, r in chunk], settings)
        job = PrintJob(request_id=req.id, seq_in_request=seq_in_request, printer_id=printer.id, kind="print",
                       payload_zpl=payload, status="rendered", created_by=user.id)
        db.add(job)
        await db.flush()
        job_ids.append(job.id)
        for seq_in_job, (p, index, serial, snap, result) in enumerate(chunk, start=1):
            db.add(PrintedLabel(job_id=job.id, seq_in_job=seq_in_job, part_id=p.part.id, label_config_id=p.config.id,
                                serial_value=serial, group_id=p.group.id if p.group else None,
                                group_index=index if p.group else None, copies=p.item.copies, snapshot=snap,
                                qr_payload=result.qr_payload, dpi=printer.dpi, bitmap_png=result.png,
                                bitmap_sha256=sha256(result.png)))
    req.request_body = body.model_dump(mode="json") | {"group_ids": group_ids}
    await db.commit()
    await queue_jobs(db, job_ids)
    return await request_out(db, req)


async def resolve_group(db: AsyncSession, p: Planned, box: ManualBox, user_id: uuid.UUID) -> LabelGroup:
    """The group row is created on the first print of a box set; later single boxes reuse it (9.3)."""
    g = p.item.group
    assert g is not None
    if g.group_id is not None:
        group = await db.get(LabelGroup, g.group_id)
        if group is None or group.part_id != p.part.id or group.total != g.total:
            raise ApiError("NOT_FOUND")
        return group
    group = LabelGroup(part_id=p.part.id, noun=box.noun, total=g.total, created_by=user_id)
    db.add(group)
    await db.flush()
    return group
