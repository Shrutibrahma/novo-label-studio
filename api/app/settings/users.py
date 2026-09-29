"""GET/POST/PATCH /users, /users/{id} (section 6; Settings → Users in 12.13)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.audit import audit
from app.auth.deps import DB, Admin
from app.auth.passwords import hash_secret
from app.auth.sessions import delete_user_sessions
from app.errors import ApiError
from app.models import AppUser
from app.setup_router import validate_account

router = APIRouter(prefix="/users", tags=["users"])

Role = Literal["admin", "operator"]


class UserRow(BaseModel):
    id: str
    username: str
    display_name: str
    role: str
    active: bool
    last_login_at: datetime | None
    created_at: datetime


class UserCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    username: str = Field(min_length=1, max_length=64)
    role: Role
    password: str = Field(max_length=1024)


class UserPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Role | None = None
    active: bool | None = None
    password: str | None = Field(default=None, max_length=1024)


def row(u: AppUser) -> UserRow:
    return UserRow(id=str(u.id), username=u.username, display_name=u.display_name, role=u.role, active=u.active,
                   last_login_at=u.last_login_at, created_at=u.created_at)


def public(u: AppUser) -> dict[str, object]:
    return {"username": u.username, "display_name": u.display_name, "role": u.role, "active": u.active}


@router.get("", response_model=list[UserRow])
async def list_users(_: Admin, db: DB) -> list[UserRow]:
    users = (await db.execute(select(AppUser).order_by(func.lower(AppUser.display_name)))).scalars()
    return [row(u) for u in users]


@router.post("", response_model=UserRow, status_code=201)
async def create_user(body: UserCreate, actor: Admin, db: DB) -> UserRow:
    username = body.username.strip()
    validate_account(username, body.password, None)
    taken = (await db.execute(select(AppUser.id).where(func.lower(AppUser.username) == username.lower()))).first()
    if taken:
        raise ApiError("USERNAME_TAKEN", fields={"username": "This username is already taken."})
    u = AppUser(username=username, display_name=body.display_name.strip(), role=body.role,
                password_hash=hash_secret(body.password))
    db.add(u)
    await db.flush()
    audit(db, actor.id, "user.create", "app_user", u.id, None, public(u))
    await db.commit()
    await db.refresh(u)
    return row(u)


async def active_admins(db: DB) -> int:
    return int((await db.execute(select(func.count()).select_from(AppUser)
                                 .where(AppUser.role == "admin", AppUser.active.is_(True)))).scalar_one())


@router.patch("/{user_id}", response_model=UserRow)
async def patch_user(user_id: uuid.UUID, body: UserPatch, actor: Admin, db: DB) -> UserRow:
    u = await db.get(AppUser, user_id, with_for_update=True)
    if u is None:
        raise ApiError("NOT_FOUND")
    before = public(u)
    losing_admin = u.role == "admin" and u.active and (
        (body.role is not None and body.role != "admin") or body.active is False)
    if losing_admin:
        # Lock all admin rows so two concurrent demotions can't both pass the check.
        await db.execute(select(AppUser.id).where(AppUser.role == "admin").with_for_update())
        if await active_admins(db) <= 1:
            raise ApiError("LAST_ADMIN")
    if body.display_name is not None:
        u.display_name = body.display_name.strip()
    if body.role is not None:
        u.role = body.role
    if body.active is not None:
        u.active = body.active
    password_changed = False
    if body.password is not None:
        validate_account(u.username, body.password, None)
        u.password_hash = hash_secret(body.password)
        u.failed_login_count = 0
        u.first_failed_at = None
        u.locked_until = None
        password_changed = True
    after = public(u)
    if password_changed or u.active is False:
        await delete_user_sessions(db, u.id)
    if after != before or password_changed:
        audit(db, actor.id, "user.update", "app_user", u.id, before,
              after | ({"password": "reset"} if password_changed else {}))
    await db.commit()
    await db.refresh(u)
    return row(u)
