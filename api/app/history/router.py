"""History, label detail, exact reprint, serial lookup and void (sections 6, 9.5, 12.12; flow 13.8)."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from anyio import to_thread
from fastapi import APIRouter, Header, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import audit
from app.auth.deps import DB, Admin, AnyUser
from app.auth.sessions import now_utc
from app.configs.spec import parse_spec
from app.errors import ApiError
from app.models import (
    IssuedSerial,
    LabelConfig,
    LabelSize,
    Printer,
    PrintedLabel,
    PrintJob,
    PrintRequest,
)
from app.printing.jobs import assert_printer_ready, printer_settings, queue_jobs
from app.printing.print_router import PrintOut, existing_request, parse_key, request_out
from app.render.canvas import sha256
from app.render.service import render_context, render_snapshot
from app.render.snapshot import CORE_LABELS, field_labels
from app.render.zpl import job_payload, load_bitmap

router = APIRouter(tags=["history"])

ReprintReason = Literal["damaged", "missing", "print_issue", "other"]


class HistoryRow(BaseModel):
    id: str
    created_at: datetime
    part_id: str
    part_number: str
    label_name: str | None
    part_name: str | None
    serial: str | None
    box: str | None
    size: str
    size_name: str
    copies: int
    by: str
    status: str
    kind: str
    reprint_of: str | None


class HistoryPage(BaseModel):
    items: list[HistoryRow]
    next_cursor: str | None


class SnapshotField(BaseModel):
    key: str
    label: str
    value: str


class TimelineEntry(BaseModel):
    status: str
    at: datetime


class JobInfo(BaseModel):
    id: str
    printer: str
    status: str
    error: str | None
    reprint_reason: str | None
    timeline: list[TimelineEntry]


class SerialInfo(BaseModel):
    value: str
    status: str
    void_reason: str | None
    allocated_at: datetime
    status_changed_at: datetime


class LabelDetail(BaseModel):
    row: HistoryRow
    bitmap_png_base64: str
    width_dots: int
    height_dots: int
    dpi: int
    printer_dpi: int
    config_version: int
    qr_payload: str | None
    fields: list[SnapshotField]
    job: JobInfo
    reprints: list[HistoryRow]
    serial: SerialInfo | None


class ReprintIn(BaseModel):
    reason: ReprintReason
    note: str | None = Field(default=None, max_length=500)


class VoidIn(BaseModel):
    reason: str = Field(max_length=500)


class SerialRecord(BaseModel):
    serial: SerialInfo
    part_id: str
    labels: list[HistoryRow]


class Person(BaseModel):
    id: str
    display_name: str


_ROWS = """
SELECT pl.id, pl.created_at, pl.part_id, p.part_number AS current_number, pl.snapshot, pl.serial_value,
       pl.group_index, g.total AS group_total, s.name AS size_name, s.width_in, s.height_in, pl.copies,
       u.display_name AS by, j.status, j.kind, pl.reprint_of, p.part_name AS current_name,
       ln.alias AS current_label
  FROM printed_label pl
  JOIN print_job j ON j.id = pl.job_id
  JOIN part p ON p.id = pl.part_id
  JOIN label_config c ON c.id = pl.label_config_id
  JOIN label_size s ON s.id = c.label_size_id
  JOIN app_user u ON u.id = j.created_by
  LEFT JOIN label_group g ON g.id = pl.group_id
  LEFT JOIN part_alias ln ON ln.part_id = p.id AND ln.is_label_name
"""


def _inches(v: Any) -> str:
    return f"{float(v):g}"


def history_row(r: Any) -> HistoryRow:
    snap = r.snapshot or {}
    part = snap.get("part", {})
    return HistoryRow(
        id=str(r.id), created_at=r.created_at, part_id=str(r.part_id),
        part_number=str(part.get("part_number") or r.current_number),
        label_name=part.get("label_name") or r.current_label, part_name=part.get("part_name") or r.current_name,
        serial=r.serial_value, box=f"{r.group_index}/{r.group_total}" if r.group_index else None,
        size=f"{_inches(r.width_in)} × {_inches(r.height_in)} in", size_name=r.size_name, copies=r.copies, by=r.by,
        status=r.status, kind=r.kind, reprint_of=str(r.reprint_of) if r.reprint_of else None,
    )


def _like(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


@router.get("/history", response_model=HistoryPage)
async def list_history(
    _: AnyUser, db: DB,
    q: Annotated[str | None, Query(max_length=200)] = None,
    part_id: uuid.UUID | None = None,
    serial: str | None = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    user_id: uuid.UUID | None = None,
    reprints_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> HistoryPage:
    where: list[str] = []
    params: dict[str, Any] = {"lim": limit + 1}
    if q and q.strip():
        where.append("(pl.serial_value ILIKE :q OR p.part_number_norm LIKE upper(:q) OR "
                     "(pl.snapshot -> 'part' ->> 'label_name') ILIKE :q OR ln.alias ILIKE :q)")
        params["q"] = _like(q.strip())
    if part_id:
        where.append("pl.part_id = :part")
        params["part"] = part_id
    if serial:
        where.append("pl.serial_value = :serial")
        params["serial"] = serial.strip()
    if from_:
        where.append("pl.created_at >= :from_")
        params["from_"] = from_
    if to:
        where.append("pl.created_at < :to")
        params["to"] = to
    if user_id:
        where.append("j.created_by = :user")
        params["user"] = user_id
    if reprints_only:
        where.append("pl.reprint_of IS NOT NULL")
    if cursor:
        try:
            c = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        except (ValueError, json.JSONDecodeError) as exc:
            raise ApiError("NOT_FOUND") from exc
        where.append("(pl.created_at, pl.id) < (CAST(:ct AS timestamptz), CAST(:ci AS uuid))")
        params.update(ct=c["t"], ci=c["i"])
    sql = f"{_ROWS} {'WHERE ' + ' AND '.join(where) if where else ''} ORDER BY pl.created_at DESC, pl.id DESC LIMIT :lim"
    rows = (await db.execute(text(sql), params)).all()
    more = len(rows) > limit
    rows = rows[:limit]
    nxt = None
    if more and rows:
        nxt = base64.urlsafe_b64encode(json.dumps({"t": rows[-1].created_at.isoformat(), "i": str(rows[-1].id)})
                                       .encode()).decode().rstrip("=")
    return HistoryPage(items=[history_row(r) for r in rows], next_cursor=nxt)


@router.get("/history/people", response_model=list[Person])
async def printed_by(_: AnyUser, db: DB) -> list[Person]:
    """Everyone who has printed something, for the History "Printed by" filter (any role)."""
    rows = (await db.execute(text("SELECT DISTINCT u.id, u.display_name FROM print_job j JOIN app_user u ON u.id = j.created_by "
                                  "WHERE j.kind <> 'test' ORDER BY u.display_name"))).all()
    return [Person(id=str(r.id), display_name=r.display_name) for r in rows]


async def _row(db: AsyncSession, label_id: uuid.UUID) -> Any:
    row = (await db.execute(text(f"{_ROWS} WHERE pl.id = :id"), {"id": label_id})).first()
    if row is None:
        raise ApiError("NOT_FOUND")
    return row


def serial_info(s: IssuedSerial) -> SerialInfo:
    return SerialInfo(value=s.value, status=s.status, void_reason=s.void_reason, allocated_at=s.allocated_at,
                      status_changed_at=s.status_changed_at)


def _display(value: Any, noun: str | None = None) -> str:
    if isinstance(value, dict) and "index" in value:
        return f"{noun or 'BOX'} {value['index']}/{value['total']}"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return "" if value is None else str(value)


@router.get("/labels/{label_id}", response_model=LabelDetail)
async def label_detail(label_id: uuid.UUID, _: AnyUser, db: DB) -> LabelDetail:
    label = await db.get(PrintedLabel, label_id)
    if label is None:
        raise ApiError("NOT_FOUND")
    row = history_row(await _row(db, label_id))
    job = await db.get(PrintJob, label.job_id)
    cfg = await db.get(LabelConfig, label.label_config_id)
    assert job is not None and cfg is not None
    printer = await db.get(Printer, job.printer_id)
    default_printer = (await db.execute(select(Printer).where(Printer.is_default.is_(True)))).scalar_one_or_none()
    ctx_labels = (await render_context(db)).custom_labels
    spec = parse_spec(cfg.spec)
    labels = field_labels(spec, ctx_labels) | CORE_LABELS
    fields: list[SnapshotField] = []
    for k, v in label.snapshot.get("part", {}).items():
        fields.append(SnapshotField(key=k, label=labels.get(k, k), value=_display(v)))
    for k, v in label.snapshot.get("manual", {}).items():
        mdef = spec.manual(k)
        noun = getattr(mdef, "noun", None)
        fields.append(SnapshotField(key=f"manual.{k}", label=mdef.label if mdef else k, value=_display(v, noun)))
    gen = label.snapshot.get("generated", {})
    for k in ("serial", "print_date"):
        if gen.get(k):
            fields.append(SnapshotField(key=k, label=CORE_LABELS[k], value=str(gen[k])))
    timeline = [TimelineEntry(status="created", at=job.created_at)]
    if job.claimed_at:
        timeline.append(TimelineEntry(status="sending", at=job.claimed_at))
    if job.sent_at:
        timeline.append(TimelineEntry(status="sent", at=job.sent_at))
    if job.finished_at:
        timeline.append(TimelineEntry(status=job.status, at=job.finished_at))
    root = label.reprint_of or label.id
    reprint_rows = (await db.execute(text(f"{_ROWS} WHERE pl.reprint_of = :r ORDER BY pl.created_at"), {"r": root})).all()
    serial = await db.get(IssuedSerial, label.serial_value) if label.serial_value else None
    img = load_bitmap(label.bitmap_png)
    return LabelDetail(
        row=row, bitmap_png_base64=base64.b64encode(label.bitmap_png).decode("ascii"), width_dots=img.size[0],
        height_dots=img.size[1], dpi=label.dpi, printer_dpi=default_printer.dpi if default_printer else label.dpi,
        config_version=cfg.version, qr_payload=label.qr_payload, fields=fields,
        job=JobInfo(id=str(job.id), printer=printer.name if printer else "", status=job.status, error=job.error,
                    reprint_reason=job.reprint_reason, timeline=timeline),
        reprints=[history_row(r) for r in reprint_rows if str(r.id) != str(label.id)],
        serial=serial_info(serial) if serial else None,
    )


@router.get("/labels/{label_id}/bitmap")
async def label_bitmap(label_id: uuid.UUID, _: AnyUser, db: DB) -> Response:
    label = await db.get(PrintedLabel, label_id)
    if label is None:
        raise ApiError("NOT_FOUND")
    return Response(label.bitmap_png, media_type="image/png", headers={"Cache-Control": "private, max-age=31536000, immutable"})


@router.post("/labels/{label_id}/reprint", response_model=PrintOut)
async def reprint(label_id: uuid.UUID, body: ReprintIn, user: AnyUser, db: DB,
                  idempotency_key: Annotated[str | None, Header()] = None) -> PrintOut:
    """9.5: a new job (kind reprint) with the original's snapshot, serial and exact bitmap. If the default
    printer's DPI differs, the label is re-rendered from the snapshot instead."""
    key = parse_key(idempotency_key)
    if (prior := await existing_request(db, key)) is not None:
        return await request_out(db, prior)
    label = await db.get(PrintedLabel, label_id)
    if label is None:
        raise ApiError("NOT_FOUND")
    original = await db.get(PrintedLabel, label.reprint_of) if label.reprint_of else label
    assert original is not None
    if original.serial_value:
        serial = await db.get(IssuedSerial, original.serial_value)
        if serial is not None and serial.status == "voided":
            raise ApiError("SERIAL_VOIDED")
    printer = (await db.execute(select(Printer).where(Printer.is_default.is_(True)))).scalar_one_or_none()
    if printer is None:
        raise ApiError("NOT_FOUND")
    await assert_printer_ready(db, printer)

    png = original.bitmap_png
    if printer.dpi != original.dpi:
        cfg = await db.get(LabelConfig, original.label_config_id)
        assert cfg is not None
        size = await db.get(LabelSize, cfg.label_size_id)
        assert size is not None
        spec = parse_spec(cfg.spec)
        ctx = await render_context(db, printer)
        result = await to_thread.run_sync(render_snapshot, original.snapshot, spec, cfg.qr_mode, size, printer,
                                          field_labels(spec, ctx.custom_labels))
        png = result.png

    req = PrintRequest(idempotency_key=key, kind="reprint",
                       request_body={"label_id": str(label_id), "reason": body.reason, "note": body.note},
                       created_by=user.id)
    db.add(req)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        prior = await existing_request(db, key)
        if prior is None:
            raise
        return await request_out(db, prior)
    payload = await to_thread.run_sync(job_payload, [(png, original.copies)], printer_settings(printer))
    job = PrintJob(request_id=req.id, seq_in_request=1, printer_id=printer.id, kind="reprint", payload_zpl=payload,
                   status="rendered", reprint_reason=body.reason, created_by=user.id)
    db.add(job)
    await db.flush()
    db.add(PrintedLabel(job_id=job.id, seq_in_job=1, part_id=original.part_id, label_config_id=original.label_config_id,
                        serial_value=original.serial_value, group_id=original.group_id, group_index=original.group_index,
                        copies=original.copies, snapshot=original.snapshot, qr_payload=original.qr_payload,
                        dpi=printer.dpi, bitmap_png=png, bitmap_sha256=sha256(png), reprint_of=original.id))
    await db.commit()
    await queue_jobs(db, [job.id])
    return await request_out(db, req)


@router.get("/serials/{value}", response_model=SerialRecord)
async def serial_lookup(value: str, _: AnyUser, db: DB) -> SerialRecord:
    serial = await db.get(IssuedSerial, value.strip())
    if serial is None:
        raise ApiError("NOT_FOUND")
    rows = (await db.execute(text(f"{_ROWS} WHERE pl.serial_value = :s ORDER BY pl.created_at"), {"s": serial.value})).all()
    return SerialRecord(serial=serial_info(serial), part_id=str(serial.part_id), labels=[history_row(r) for r in rows])


@router.post("/serials/{value}/void", response_model=SerialInfo)
async def void_serial(value: str, body: VoidIn, user: Admin, db: DB) -> SerialInfo:
    reason = body.reason.strip()
    if len(reason) < 5:
        raise ApiError("VOID_REASON_SHORT", fields={"reason": "Reason must be at least 5 characters."})
    serial = await db.get(IssuedSerial, value.strip(), with_for_update=True)
    if serial is None:
        raise ApiError("NOT_FOUND")
    if serial.status == "voided":
        raise ApiError("SERIAL_VOIDED")
    before = {"status": serial.status}
    serial.status, serial.void_reason, serial.status_changed_at = "voided", reason, now_utc()
    audit(db, user.id, "serial.void", "issued_serial", serial.value, before, {"status": "voided", "void_reason": reason})
    await db.commit()
    return serial_info(serial)

