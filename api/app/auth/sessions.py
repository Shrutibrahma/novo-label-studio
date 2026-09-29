"""Server-side sessions: the cookie carries a random 32-byte token; only its sha256 is stored (section 15)."""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Response
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.errors import ApiError
from app.models import AppUser, UserSession

COOKIE_NAME = "ls_session"
TOUCH_INTERVAL = timedelta(seconds=60)


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    username: str
    display_name: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def now_utc() -> datetime:
    return datetime.now(UTC)


def token_digest(token: str) -> bytes:
    return hashlib.sha256(token.encode("ascii")).digest()


def new_token() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")


def ttl() -> timedelta:
    return timedelta(hours=get_settings().session_ttl_hours)


async def create_session(db: AsyncSession, user_id: uuid.UUID, user_agent: str | None) -> str:
    token = new_token()
    now = now_utc()
    db.add(UserSession(token_sha256=token_digest(token), user_id=user_id, created_at=now, last_seen_at=now,
                       expires_at=now + ttl(), user_agent=(user_agent or "")[:300] or None))
    return token


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(COOKIE_NAME, token, httponly=True, secure=get_settings().cookie_secure,
                        samesite="lax", path="/")


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, secure=get_settings().cookie_secure,
                           samesite="lax")


async def resolve_session(db: AsyncSession, token: str | None) -> CurrentUser:
    if not token:
        raise ApiError("SESSION_EXPIRED")
    try:
        digest = token_digest(token)
    except UnicodeEncodeError as exc:
        raise ApiError("SESSION_EXPIRED") from exc
    row = (await db.execute(
        select(UserSession, AppUser).join(AppUser, AppUser.id == UserSession.user_id)
        .where(UserSession.token_sha256 == digest)
    )).first()
    if row is None:
        raise ApiError("SESSION_EXPIRED")
    sess, user = row
    now = now_utc()
    if sess.expires_at <= now or not user.active:
        await db.execute(delete(UserSession).where(UserSession.token_sha256 == digest))
        await db.commit()
        raise ApiError("SESSION_EXPIRED")
    if now - sess.last_seen_at >= TOUCH_INTERVAL:
        # 12 h idle expiry: every touch pushes expiry out again.
        await db.execute(update(UserSession).where(UserSession.token_sha256 == digest)
                         .values(last_seen_at=now, expires_at=now + ttl()))
        await db.commit()
    return CurrentUser(id=user.id, username=user.username, display_name=user.display_name, role=user.role)


async def delete_session(db: AsyncSession, token: str) -> None:
    await db.execute(delete(UserSession).where(UserSession.token_sha256 == token_digest(token)))


async def delete_user_sessions(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(delete(UserSession).where(UserSession.user_id == user_id))
