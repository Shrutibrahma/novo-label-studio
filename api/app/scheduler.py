"""Background maintenance loop. A Postgres advisory lock makes sure only one API process runs each tick."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.sessions import now_utc
from app.db import sessionmaker
from app.models import UserSession

log = logging.getLogger("app.scheduler")

TICK_SECONDS = 5.0
LOCK_KEY = 7_202_609_30

Task = Callable[[AsyncSession], Awaitable[None]]


async def expire_sessions(db: AsyncSession) -> None:
    await db.execute(delete(UserSession).where(UserSession.expires_at <= now_utc()))


TASKS: list[Task] = [expire_sessions]


def register(task: Task) -> None:
    if task not in TASKS:
        TASKS.append(task)


async def run_once() -> None:
    async with sessionmaker()() as db:
        got = (await db.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": LOCK_KEY})).scalar()
        if not got:
            await db.rollback()
            return
        for task in TASKS:
            try:
                async with db.begin_nested():
                    await task(db)
            except Exception:
                log.exception("scheduled task %s failed", task.__name__)
        await db.commit()


async def _loop() -> None:
    while True:
        try:
            await run_once()
        except Exception:
            log.exception("scheduler tick failed")
        await asyncio.sleep(TICK_SECONDS)


def start() -> asyncio.Task[None]:
    return asyncio.create_task(_loop(), name="scheduler")


async def stop(task: asyncio.Task[None]) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
