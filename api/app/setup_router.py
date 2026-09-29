"""GET /setup/status and POST /setup (section 6, screen 12.3, seed data in section 5)."""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import exists, select, text

from app.audit import audit
from app.auth.deps import DB
from app.auth.passwords import MIN_PASSWORD_LENGTH, hash_secret
from app.auth.router import UserOut, user_out
from app.auth.sessions import create_session, now_utc, set_session_cookie
from app.configs.defaults import (
    DEFAULT_SIZE_NAME,
    DEFAULT_SPEC,
    PRESET_SIZES,
    PRINTER_PROFILE,
    SETTING_COMPANY,
)
from app.errors import ApiError, field_error
from app.models import AppSetting, AppUser, LabelConfig, LabelSize, Printer, PrintAgent, SerialSequence
from app.printing.agent_auth import issue_token

router = APIRouter(prefix="/setup", tags=["setup"])

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,64}$")
PREFIX_RE = re.compile(r"^[A-Z0-9]{1,12}$")
SETUP_LOCK_KEY = 7_202_609_29  # pg advisory lock id; serializes concurrent POST /setup calls


class SetupStatus(BaseModel):
    needs_setup: bool


class SetupIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(max_length=1024)
    confirm_password: str = Field(max_length=1024)
    company_name: str = Field(min_length=1, max_length=120)
    serial_prefix: str = Field(min_length=1, max_length=12)
    starting_number: int = Field(ge=1)
    digits: int = Field(ge=4, le=12)


class SetupOut(BaseModel):
    user: UserOut
    agent_token: str
    printer_id: str


async def users_exist(db: DB) -> bool:
    return bool((await db.execute(select(exists().where(AppUser.id.is_not(None))))).scalar())


@router.get("/status", response_model=SetupStatus)
async def setup_status(db: DB) -> SetupStatus:
    return SetupStatus(needs_setup=not await users_exist(db))


def validate_account(username: str, password: str, confirm: str | None) -> None:
    if not USERNAME_RE.match(username):
        raise ApiError("USERNAME_INVALID", fields={"username": "Username can use 3–64 letters, numbers, "
                                                   "dots, dashes and underscores."})
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ApiError("PASSWORD_TOO_SHORT", fields={"password": "Password must be at least 12 characters."})
    if confirm is not None and confirm != password:
        raise ApiError("PASSWORDS_DIFFERENT", fields={"confirm_password": "The passwords don't match."})


@router.post("", response_model=SetupOut)
async def run_setup(body: SetupIn, request: Request, response: Response, db: DB) -> SetupOut:
    username = body.username.strip()
    validate_account(username, body.password, body.confirm_password)
    prefix = body.serial_prefix.strip().upper()
    if not PREFIX_RE.match(prefix):
        raise ApiError("SERIAL_PREFIX_INVALID",
                       fields={"serial_prefix": "Serial prefix can use 1–12 capital letters and numbers."})
    if body.starting_number >= 10 ** body.digits:
        raise field_error("FIELD_OUT_OF_RANGE", "starting_number", "Starting number", min=1,
                          max=10 ** body.digits - 1)

    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": SETUP_LOCK_KEY})
    if await users_exist(db):
        raise ApiError("SETUP_DONE")

    now = now_utc()
    admin = AppUser(username=username, display_name=body.display_name.strip(), role="admin",
                    password_hash=hash_secret(body.password), last_login_at=now)
    db.add(admin)
    await db.flush()
    audit(db, admin.id, "user.create", "app_user", admin.id, None,
          {"username": admin.username, "display_name": admin.display_name, "role": admin.role})

    db.add(AppSetting(key=SETTING_COMPANY, value=body.company_name.strip(), updated_by=admin.id))

    seq = SerialSequence(name="Default", prefix=prefix, separator="-", digits=body.digits,
                         next_value=body.starting_number)
    db.add(seq)

    sizes: dict[str, LabelSize] = {}
    for name, w, h in PRESET_SIZES:
        size = LabelSize(name=name, width_in=w, height_in=h)
        db.add(size)
        sizes[name] = size
    await db.flush()
    audit(db, admin.id, "serial.update", "serial_sequence", seq.id, None,
          {"prefix": prefix, "separator": "-", "digits": body.digits, "next_value": body.starting_number})
    for size in sizes.values():
        audit(db, admin.id, "size.create", "label_size", size.id, None,
              {"name": size.name, "width_in": size.width_in, "height_in": size.height_in})

    token, token_hash = issue_token()
    agent = PrintAgent(name="Laptop agent", token_hash=token_hash)
    db.add(agent)
    await db.flush()
    printer = Printer(agent_id=agent.id, is_default=True, **PRINTER_PROFILE)
    db.add(printer)
    await db.flush()
    audit(db, admin.id, "printer.update", "printer", printer.id, None,
          {k: v for k, v in PRINTER_PROFILE.items()} | {"agent_id": agent.id, "is_default": True})

    config = LabelConfig(config_key=uuid.uuid4(), version=1, scope="default", part_id=None,
                         label_size_id=sizes[DEFAULT_SIZE_NAME].id, spec=DEFAULT_SPEC, qr_mode="none",
                         serial_mode="none", serial_sequence_id=None, created_by=admin.id)
    db.add(config)
    await db.flush()
    audit(db, admin.id, "config.publish", "label_config", config.id, None,
          {"scope": "default", "version": 1, "label_size_id": config.label_size_id, "spec": DEFAULT_SPEC,
           "qr_mode": "none", "serial_mode": "none"})

    session_token = await create_session(db, admin.id, request.headers.get("user-agent"))
    await db.commit()
    set_session_cookie(response, session_token)
    request.state.user_id = admin.id
    return SetupOut(user=user_out(admin), agent_token=token, printer_id=str(printer.id))
