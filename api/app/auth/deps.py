"""Role guards used by every router."""

from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.sessions import COOKIE_NAME, CurrentUser, resolve_session
from app.db import get_db
from app.errors import ApiError

DB = Annotated[AsyncSession, Depends(get_db)]


async def current_user(request: Request, db: DB,
                       ls_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None) -> CurrentUser:
    user = await resolve_session(db, ls_session)
    request.state.user_id = user.id
    return user


async def admin_user(user: Annotated[CurrentUser, Depends(current_user)]) -> CurrentUser:
    if not user.is_admin:
        raise ApiError("FORBIDDEN")
    return user


AnyUser = Annotated[CurrentUser, Depends(current_user)]
Admin = Annotated[CurrentUser, Depends(admin_user)]
