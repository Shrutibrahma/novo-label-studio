"""Effective printer status and the print-blocking rules of section 14.1."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.auth.sessions import now_utc
from app.errors import ApiError

AGENT_STALE_AFTER = timedelta(seconds=30)

PRINTER_STATUSES = ("ready", "printing", "offline", "out_of_media", "head_open", "paused", "error", "unknown")

BLOCKING = {
    "offline": "PRINTER_OFFLINE",
    "out_of_media": "PRINTER_OUT_OF_MEDIA",
    "head_open": "PRINTER_HEAD_OPEN",
    "paused": "PRINTER_PAUSED",
    "error": "PRINTER_ERROR",
}


def agent_is_stale(last_seen_at: datetime | None, now: datetime | None = None) -> bool:
    return last_seen_at is None or (now or now_utc()) - last_seen_at > AGENT_STALE_AFTER


def effective_status(reported: str, agent_last_seen: datetime | None) -> str:
    """Section 12.1: agent last seen > 30 s ago -> Offline regardless of reported status."""
    return "offline" if agent_is_stale(agent_last_seen) else reported


def assert_can_print(reported: str, agent_last_seen: datetime | None) -> None:
    """Checks in the order of the 14.2 table: printer statuses first, then the agent."""
    code = BLOCKING.get(reported)
    if code:
        raise ApiError(code)
    if agent_is_stale(agent_last_seen):
        raise ApiError("AGENT_UNREACHABLE")
