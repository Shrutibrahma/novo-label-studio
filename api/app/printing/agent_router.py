"""Agent endpoints (section 6; state machine 8.3). Only reachable with the agent's bearer token."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any, Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import DB
from app.auth.sessions import now_utc
from app.errors import ApiError, message_for
from app.models import IssuedSerial, Printer, PrintedLabel, PrintJob
from app.printing.agent_auth import CurrentAgent

router = APIRouter(prefix="/agent", tags=["agent"])

LEASE = timedelta(seconds=60)
PrinterStatus = Literal["ready", "printing", "offline", "out_of_media", "head_open", "paused", "error", "unknown"]


class JobPayload(BaseModel):
    id: str
    printer_id: str
    kind: str
    zpl: str


class StatusIn(BaseModel):
    status: Literal["sent", "confirmed", "failed"]
    error: str | None = Field(default=None, max_length=2000)


class HeartbeatIn(BaseModel):
    printer_status: PrinterStatus
    host_info: dict[str, Any] = Field(default_factory=dict)


async def touch(db: AsyncSession, agent_id: uuid.UUID) -> None:
    await db.execute(text("UPDATE print_agent SET last_seen_at = now() WHERE id = :a"), {"a": agent_id})


async def set_serials(db: AsyncSession, job_id: uuid.UUID, to: str, from_statuses: tuple[str, ...]) -> None:
    serials = select(PrintedLabel.serial_value).where(PrintedLabel.job_id == job_id,
                                                      PrintedLabel.serial_value.is_not(None))
    await db.execute(update(IssuedSerial).where(IssuedSerial.value.in_(serials), IssuedSerial.status.in_(from_statuses))
                     .values(status=to, status_changed_at=now_utc()))


@router.get("/jobs/next", response_model=JobPayload, responses={204: {"description": "Nothing to do"}})
async def next_job(agent: CurrentAgent, db: DB) -> Any:
    """Claims the oldest queued job for this agent's printers (FOR UPDATE SKIP LOCKED): queued → sending."""
    await touch(db, agent.id)
    row = (await db.execute(text("""
        UPDATE print_job SET status = 'sending', claimed_at = now()
         WHERE id = (SELECT j.id FROM print_job j JOIN printer p ON p.id = j.printer_id
                      WHERE j.status = 'queued' AND p.agent_id = :agent
                      ORDER BY j.created_at, j.seq_in_request NULLS FIRST
                      FOR UPDATE OF j SKIP LOCKED LIMIT 1)
        RETURNING id, printer_id, kind, payload_zpl"""), {"agent": agent.id})).first()
    await db.commit()
    if row is None:
        return Response(status_code=204)
    return JobPayload(id=str(row.id), printer_id=str(row.printer_id), kind=row.kind, zpl=bytes(row.payload_zpl).decode("ascii"))


@router.post("/jobs/{job_id}/status", status_code=204)
async def job_status(job_id: uuid.UUID, body: StatusIn, agent: CurrentAgent, db: DB) -> Response:
    job = await db.get(PrintJob, job_id, with_for_update=True)
    printer = await db.get(Printer, job.printer_id) if job else None
    if job is None or printer is None or printer.agent_id != agent.id:
        raise ApiError("NOT_FOUND")
    now = now_utc()
    if body.status == "sent" and job.status == "sending":
        job.status, job.sent_at = "sent", now
        await set_serials(db, job.id, "printed", ("allocated", "unconfirmed"))
    elif body.status == "failed" and job.status == "sending":
        job.status, job.finished_at = "failed", now
        job.error = (body.error or "").strip()[:500] or "Print failed"
        await set_serials(db, job.id, "unconfirmed", ("allocated",))
    elif body.status == "confirmed" and job.status in ("sending", "sent"):  # [SPIKE] printer readback
        job.sent_at = job.sent_at or now
        job.status, job.finished_at = "confirmed", now
        await set_serials(db, job.id, "printed", ("allocated", "unconfirmed"))
    else:
        raise ApiError("INVALID_STATE")
    await touch(db, agent.id)
    await db.commit()
    return Response(status_code=204)


@router.post("/heartbeat", status_code=204)
async def heartbeat(body: HeartbeatIn, agent: CurrentAgent, db: DB) -> Response:
    """Every 10 s: printer status mapped by the agent (8.2 step 4) and host info."""
    agent.host_info = body.host_info
    agent.last_seen_at = now_utc()
    await db.execute(update(Printer).where(Printer.agent_id == agent.id)
                     .values(last_status=body.printer_status, last_status_at=now_utc()))
    await db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- scheduled: lease + stuck rendered jobs
async def expire_leases(db: AsyncSession) -> None:
    """sending → failed when no update arrives within 60 s of the claim; serials become unconfirmed (8.3)."""
    stale = (await db.execute(select(PrintJob).where(PrintJob.status == "sending",
                                                     PrintJob.claimed_at < now_utc() - LEASE)
                              .with_for_update(skip_locked=True))).scalars().all()
    for job in stale:
        job.status, job.finished_at = "failed", now_utc()
        job.error = message_for("AGENT_UNREACHABLE")
        await set_serials(db, job.id, "unconfirmed", ("allocated",))


async def queue_rendered(db: AsyncSession) -> None:
    """A job whose 'queued' step was lost (API restart right after commit) is queued by the next tick."""
    await db.execute(update(PrintJob).where(PrintJob.status == "rendered",
                                            PrintJob.created_at < now_utc() - timedelta(seconds=10))
                     .values(status="queued"))
