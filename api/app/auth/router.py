"""POST /auth/login, POST /auth/logout, GET /auth/me (section 6)."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Cookie, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.auth.deps import DB, AnyUser
from app.auth.passwords import hash_secret, verify_secret
from app.auth.sessions import (
    COOKIE_NAME,
    clear_session_cookie,
    create_session,
    delete_session,
    now_utc,
    set_session_cookie,
)
from app.errors import ApiError
from app.models import AppUser

router = APIRouter(prefix="/auth", tags=["auth"])

LOCK_WINDOW = timedelta(minutes=15)
LOCK_DURATION = timedelta(minutes=15)
MAX_FAILURES = 5
# Verified against when the username doesn't exist, so response time doesn't reveal valid usernames.
_DUMMY_HASH = hash_secret("not-a-real-password-0000")


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str
    role: str


def user_out(u: AppUser) -> UserOut:
    return UserOut(id=str(u.id), username=u.username, display_name=u.display_name, role=u.role)


@router.post("/login", response_model=UserOut)
async def login(body: LoginIn, request: Request, response: Response, db: DB) -> UserOut:
    user = (await db.execute(
        select(AppUser).where(func.lower(AppUser.username) == body.username.strip().lower()).with_for_update()
    )).scalar_one_or_none()
    now = now_utc()
    if user is None or not user.active:
        verify_secret(_DUMMY_HASH, body.password)
        raise ApiError("AUTH_INVALID")
    if user.locked_until is not None and user.locked_until > now:
        raise ApiError("AUTH_LOCKED")
    if not verify_secret(user.password_hash, body.password):
        if user.first_failed_at is None or now - user.first_failed_at > LOCK_WINDOW:
            user.first_failed_at = now
            user.failed_login_count = 1
        else:
            user.failed_login_count += 1
        locked = user.failed_login_count >= MAX_FAILURES
        if locked:
            user.locked_until = now + LOCK_DURATION
            user.failed_login_count = 0
            user.first_failed_at = None
        await db.commit()
        raise ApiError("AUTH_LOCKED" if locked else "AUTH_INVALID")
    user.failed_login_count = 0
    user.first_failed_at = None
    user.locked_until = None
    user.last_login_at = now
    token = await create_session(db, user.id, request.headers.get("user-agent"))
    await db.commit()
    set_session_cookie(response, token)
    request.state.user_id = user.id
    return user_out(user)


@router.post("/logout", status_code=204)
async def logout(_: AnyUser, response: Response, db: DB,
                 ls_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None) -> Response:
    if ls_session:
        await delete_session(db, ls_session)
        await db.commit()
    clear_session_cookie(response)
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
async def me(user: AnyUser, db: DB) -> UserOut:
    row = await db.get(AppUser, user.id)
    if row is None:
        raise ApiError("SESSION_EXPIRED")
    return user_out(row)
