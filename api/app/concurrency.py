"""Optimistic concurrency: If-Match: <updated_at ISO> (section 6 conventions)."""

from __future__ import annotations

from datetime import datetime

from app.errors import ApiError


def check_if_match(if_match: str | None, current: datetime) -> None:
    if if_match is None:
        return
    try:
        expected = datetime.fromisoformat(if_match.strip().strip('"').replace("Z", "+00:00"))
    except ValueError as exc:
        raise ApiError("STALE_WRITE") from exc
    if expected.tzinfo is None or abs((expected - current).total_seconds()) > 0.0005:
        raise ApiError("STALE_WRITE")
