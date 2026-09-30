"""Job read model, cancel, and the test label job (sections 6, 8.3, 12.13)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import select, update

from app.auth.deps import DB, Admin, AnyUser
from app.auth.sessions import now_utc
from app.config import APP_VERSION
from app.configs.defaults import DEFAULT_SIZE_NAME
from app.errors import ApiError
from app.models import IssuedSerial, LabelConfig, LabelSize, Printer, PrintAgent, PrintedLabel, PrintJob
from app.printing.status import assert_can_print
from app.render.canvas import canvas_for
from app.render.testlabel import render_test_label
from app.render.zpl import PrinterSettings, job_payload
from app.timeutil import format_display, request_zone

router = APIRouter(tags=["jobs"])

CANCELLED_REASON = "Cancelled before printing"


class JobLabelOut(BaseModel):
    id: str
    seq_in_job: int
    part_id: str
    serial_value: str | None
    group_index: int | None
    copies: int


class JobOut(BaseModel):
    id: str
    kind: str
    status: str
    error: str | None
    printer_id: str
    request_id: str | None
    created_at: datetime
    claimed_at: datetime | None
    sent_at: datetime | None
    finished_at: datetime | None
    labels: list[JobLabelOut]


async def job_out(db: DB, job: PrintJob) -> JobOut:
    labels = (await db.execute(select(PrintedLabel).where(PrintedLabel.job_id == job.id)
                               .order_by(PrintedLabel.seq_in_job))).scalars()
    return JobOut(
        id=str(job.id), kind=job.kind, status=job.status, error=job.error, printer_id=str(job.printer_id),
        request_id=str(job.request_id) if job.request_id else None, created_at=job.created_at,
        claimed_at=job.claimed_at, sent_at=job.sent_at, finished_at=job.finished_at,
        labels=[JobLabelOut(id=str(pl.id), seq_in_job=pl.seq_in_job, part_id=str(pl.part_id),
                            serial_value=pl.serial_value, group_index=pl.group_index, copies=pl.copies)
                for pl in labels],
    )


def printer_settings(p: Printer) -> PrinterSettings:
    return PrinterSettings(darkness=p.darkness, speed_ips=p.speed_ips, offset_x_dots=p.offset_x_dots,
                           offset_y_dots=p.offset_y_dots)


async def assert_printer_ready(db: DB, printer: Printer) -> None:
    agent = await db.get(PrintAgent, printer.agent_id)
    assert_can_print(printer.last_status, agent.last_seen_at if agent else None)


async def queue_jobs(db: DB, job_ids: list[uuid.UUID]) -> None:
    """rendered -> queued, immediately after the render transaction commits (8.3)."""
    if job_ids:
        await db.execute(update(PrintJob).where(PrintJob.id.in_(job_ids), PrintJob.status == "rendered")
                         .values(status="queued"))
        await db.commit()


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, _: AnyUser, db: DB) -> JobOut:
    job = await db.get(PrintJob, job_id)
    if job is None:
        raise ApiError("NOT_FOUND")
    return await job_out(db, job)


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
async def cancel_job(job_id: uuid.UUID, _: AnyUser, db: DB) -> JobOut:
    job = await db.get(PrintJob, job_id, with_for_update=True)
    if job is None:
        raise ApiError("NOT_FOUND")
    if job.status not in ("rendered", "queued"):
        raise ApiError("JOB_NOT_CANCELLABLE")
    job.status = "cancelled"
    job.finished_at = now_utc()
    # Voided, reason "Cancelled before printing" — only serials this job issued (a reprint's serial stays).
    if job.kind == "print":
        serials = select(PrintedLabel.serial_value).where(PrintedLabel.job_id == job.id,
                                                          PrintedLabel.serial_value.is_not(None))
        await db.execute(update(IssuedSerial).where(IssuedSerial.value.in_(serials),
                                                    IssuedSerial.status == "allocated")
                         .values(status="voided", void_reason=CANCELLED_REASON, status_changed_at=now_utc()))
    await db.commit()
    return await job_out(db, job)


@router.post("/printers/{printer_id}/test", response_model=JobOut)
async def print_test_label(printer_id: uuid.UUID, request: Request, user: Admin, db: DB) -> JobOut:
    printer = await db.get(Printer, printer_id)
    if printer is None:
        raise ApiError("NOT_FOUND")
    await assert_printer_ready(db, printer)
    size = await db.get(LabelSize, printer.loaded_label_size_id) if printer.loaded_label_size_id else None
    if size is None:
        # No size confirmed as loaded yet: use the default label's size, else the Large preset.
        size = (await db.execute(select(LabelSize).join(LabelConfig, LabelConfig.label_size_id == LabelSize.id)
                                 .where(LabelConfig.scope == "default", LabelConfig.is_current.is_(True)))
                ).scalar_one_or_none() or (await db.execute(
                    select(LabelSize).where(LabelSize.name == DEFAULT_SIZE_NAME))).scalar_one()
    zone = request_zone(request)
    w, h = f"{float(size.width_in):g}", f"{float(size.height_in):g}"
    lines = ["Novo Smart Labels test", f"{printer.name} · {printer.dpi} dpi", f"{size.name} · {w} × {h} in",
             format_display(now_utc(), zone), f"v{APP_VERSION}"]
    png = render_test_label(canvas_for(size.width_in, size.height_in, printer.print_width_in, printer.dpi), lines)
    job = PrintJob(printer_id=printer.id, kind="test", payload_zpl=job_payload([(png, 1)], printer_settings(printer)),
                   status="rendered", created_by=user.id)
    db.add(job)
    await db.commit()
    await queue_jobs(db, [job.id])
    await db.refresh(job)
    return await job_out(db, job)
