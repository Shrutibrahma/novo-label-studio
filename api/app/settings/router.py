"""GET/PATCH /settings (section 6; screen 12.13 General + Serial numbers; rules in 9.1)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import exists, select

from app.audit import audit
from app.auth.deps import DB, Admin, AnyUser
from app.configs.defaults import ALL_FONTS, SETTING_COMPANY, SETTING_FONTS
from app.errors import ApiError, field_error
from app.models import AppSetting, IssuedSerial, SerialSequence
from app.setup_router import PREFIX_RE

router = APIRouter(prefix="/settings", tags=["settings"])


class SerialSettings(BaseModel):
    id: str
    prefix: str
    separator: Literal["", "-", "_"]
    digits: int
    next_value: int
    locked: bool
    example: str


class SettingsOut(BaseModel):
    company_name: str
    serial: SerialSettings
    fonts_allowed: list[str]


class SettingsPatch(BaseModel):
    company_name: str | None = Field(default=None, min_length=1, max_length=120)
    serial_prefix: str | None = Field(default=None, min_length=1, max_length=12)
    serial_separator: Literal["", "-", "_"] | None = None
    serial_digits: int | None = Field(default=None, ge=4, le=12)
    serial_next_value: int | None = Field(default=None, ge=1)


def format_serial(prefix: str, separator: str, digits: int, value: int) -> str:
    return f"{prefix}{separator}{value:0{digits}d}"


async def get_setting(db: DB, key: str, default: Any) -> Any:
    row = await db.get(AppSetting, key)
    return row.value if row is not None else default


async def default_sequence(db: DB, lock: bool = False) -> SerialSequence:
    q = select(SerialSequence).where(SerialSequence.name == "Default")
    if lock:
        q = q.with_for_update()
    seq = (await db.execute(q)).scalar_one_or_none()
    if seq is None:
        raise ApiError("NOT_FOUND")
    return seq


async def serial_locked(db: DB, seq: SerialSequence) -> bool:
    return bool((await db.execute(select(exists().where(IssuedSerial.sequence_id == seq.id)))).scalar())


async def settings_out(db: DB) -> SettingsOut:
    seq = await default_sequence(db)
    return SettingsOut(
        company_name=str(await get_setting(db, SETTING_COMPANY, "")),
        serial=SerialSettings(id=str(seq.id), prefix=seq.prefix, separator=seq.separator,  # type: ignore[arg-type]
                              digits=seq.digits, next_value=seq.next_value, locked=await serial_locked(db, seq),
                              example=format_serial(seq.prefix, seq.separator, seq.digits, seq.next_value)),
        fonts_allowed=list(await get_setting(db, SETTING_FONTS, ALL_FONTS)),
    )


@router.get("", response_model=SettingsOut)
async def read_settings(_: AnyUser, db: DB) -> SettingsOut:
    return await settings_out(db)


@router.patch("", response_model=SettingsOut)
async def patch_settings(body: SettingsPatch, user: Admin, db: DB) -> SettingsOut:
    if body.company_name is not None:
        row = await db.get(AppSetting, SETTING_COMPANY)
        if row is None:
            db.add(AppSetting(key=SETTING_COMPANY, value=body.company_name.strip(), updated_by=user.id))
        else:
            row.value = body.company_name.strip()
            row.updated_by = user.id

    format_change = any(v is not None for v in (body.serial_prefix, body.serial_separator, body.serial_digits))
    if format_change or body.serial_next_value is not None:
        seq = await default_sequence(db, lock=True)
        before = {"prefix": seq.prefix, "separator": seq.separator, "digits": seq.digits,
                  "next_value": seq.next_value}
        if format_change:
            changed = ((body.serial_prefix is not None and body.serial_prefix.strip().upper() != seq.prefix)
                       or (body.serial_separator is not None and body.serial_separator != seq.separator)
                       or (body.serial_digits is not None and body.serial_digits != seq.digits))
            if changed and await serial_locked(db, seq):
                raise ApiError("SERIAL_SETTINGS_LOCKED")
            if body.serial_prefix is not None:
                prefix = body.serial_prefix.strip().upper()
                if not PREFIX_RE.match(prefix):
                    raise ApiError("SERIAL_PREFIX_INVALID", fields={
                        "serial_prefix": "Serial prefix can use 1–12 capital letters and numbers."})
                seq.prefix = prefix
            if body.serial_separator is not None:
                seq.separator = body.serial_separator
            if body.serial_digits is not None:
                seq.digits = body.serial_digits
        if body.serial_next_value is not None and body.serial_next_value != seq.next_value:
            if body.serial_next_value < seq.next_value:
                raise field_error("FIELD_OUT_OF_RANGE", "serial_next_value", "Next number",
                                  min=seq.next_value, max=10 ** seq.digits - 1)
            seq.next_value = body.serial_next_value
        if seq.next_value >= 10 ** seq.digits:
            raise field_error("FIELD_OUT_OF_RANGE", "serial_next_value", "Next number", min=1,
                              max=10 ** seq.digits - 1)
        after = {"prefix": seq.prefix, "separator": seq.separator, "digits": seq.digits,
                 "next_value": seq.next_value}
        if after != before:
            audit(db, user.id, "serial.update", "serial_sequence", seq.id, before, after)
    await db.commit()
    return await settings_out(db)
