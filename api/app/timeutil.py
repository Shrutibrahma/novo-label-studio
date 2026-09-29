"""Laptop-local time. The browser sends its IANA zone in X-Timezone; the server stores UTC (section 15)."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Request

UTC_ZONE = ZoneInfo("UTC")


def request_zone(request: Request | None) -> ZoneInfo:
    name = request.headers.get("x-timezone") if request is not None else None
    if not name:
        return UTC_ZONE
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return UTC_ZONE


def local_today(zone: ZoneInfo) -> date:
    return datetime.now(zone).date()


def format_display(dt: datetime, zone: ZoneInfo) -> str:
    """Section 5 invariant 5: `Sep 29, 2026, 9:34 AM`."""
    local = dt.astimezone(zone)
    hour = local.hour % 12 or 12
    ampm = "AM" if local.hour < 12 else "PM"
    return f"{local:%b} {local.day}, {local.year}, {hour}:{local.minute:02d} {ampm}"
