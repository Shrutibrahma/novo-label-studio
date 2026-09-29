"""Shared test helpers."""

from __future__ import annotations

from sqlalchemy import text

from app.db import sessionmaker


async def agent_alive(status: str = "ready") -> None:
    """Pretend the laptop agent just sent a heartbeat."""
    async with sessionmaker()() as db:
        await db.execute(text("UPDATE print_agent SET last_seen_at = now()"))
        await db.execute(text("UPDATE printer SET last_status = :s, last_status_at = now()"), {"s": status})
        await db.commit()
