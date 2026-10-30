"""GET/PATCH /settings (section 6; screen 12.13 General + Serial numbers; rules in 9.1)."""

from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import urlsplit
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import exists, select

from app.audit import audit
from app.auth.deps import DB, Admin, AnyUser
from app.config import get_settings
from app.configs.defaults import (ALL_FONTS, SETTING_COMPANY, SETTING_FONTS, SETTING_HOUSE_STYLE, SETTING_QR_LINK,
                                  SETTING_QR_LINK_BASE, SETTING_SCAN_PUBLIC)
from app.errors import ApiError, field_error
from app.models import AppSetting, IssuedSerial, SerialSequence
from app.render.house import HouseStyle
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


class BackupStatus(BaseModel):
    """The last nightly (or manual) backup, from the backup container's status file (v1.1 D25)."""

    at: datetime | None
    copy_enabled: bool
    copied: bool | None  # None: no copy folder set up when that backup ran
    copy_error: str | None


class QrSettings(BaseModel):
    """QR codes open the part page: on/off, the address phones open, and whether it needs a sign-in."""

    link: bool
    link_base: str
    scan_public: bool


class SettingsOut(BaseModel):
    company_name: str
    serial: SerialSettings
    fonts_allowed: list[str]
    backup: BackupStatus
    qr: QrSettings


class SettingsPatch(BaseModel):
    company_name: str | None = Field(default=None, min_length=1, max_length=120)
    serial_prefix: str | None = Field(default=None, min_length=1, max_length=12)
    serial_separator: Literal["", "-", "_"] | None = None
    serial_digits: int | None = Field(default=None, ge=4, le=12)
    serial_next_value: int | None = Field(default=None, ge=1)
    qr_link: bool | None = None
    qr_link_base: str | None = Field(default=None, max_length=200)
    scan_public: bool | None = None


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
        backup=backup_status(),
        qr=await qr_settings(db),
    )


async def qr_settings(db: DB) -> QrSettings:
    base = str(await get_setting(db, SETTING_QR_LINK_BASE, "") or get_settings().public_base_url)
    return QrSettings(link=bool(await get_setting(db, SETTING_QR_LINK, False)), link_base=base.rstrip("/"),
                      scan_public=bool(await get_setting(db, SETTING_SCAN_PUBLIC, False)))


def clean_link_base(raw: str) -> str:
    base = raw.strip().rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.query or parsed.fragment:
        raise ApiError("QR_LINK_INVALID", fields={"qr_link_base": "Use the address phones open, for example "
                                                                 "https://192.168.1.20:8443."})
    return base


async def put_setting(db: DB, key: str, value: Any, user_id: Any) -> None:
    row = await db.get(AppSetting, key)
    before = row.value if row is not None else None
    if before == value:
        return
    if row is None:
        db.add(AppSetting(key=key, value=value, updated_by=user_id))
    else:
        row.value = value
        row.updated_by = user_id
    audit(db, user_id, "setting.update", "app_setting", key, {"value": before}, {"value": value})


def backup_status() -> BackupStatus:
    settings = get_settings()
    try:
        raw = json.loads(settings.backup_status_file.read_text(encoding="utf-8"))
        at = datetime.fromisoformat(str(raw["at"]).replace("Z", "+00:00"))
        copied = raw.get("copied")
        error = str(raw.get("copy_error") or "") or None
    except (OSError, ValueError, KeyError, TypeError):
        at, copied, error = None, None, None
    return BackupStatus(at=at, copy_enabled=bool(settings.backup_copy_enabled.strip()),
                        copied=copied if isinstance(copied, bool) else None, copy_error=error)


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

    if body.qr_link is not None:
        await put_setting(db, SETTING_QR_LINK, body.qr_link, user.id)
    if body.qr_link_base is not None:
        await put_setting(db, SETTING_QR_LINK_BASE, clean_link_base(body.qr_link_base), user.id)
    if body.scan_public is not None:
        await put_setting(db, SETTING_SCAN_PUBLIC, body.scan_public, user.id)

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


# ---------------------------------------------------------------- label style (v1.1 D21)
async def house_style(db: DB) -> HouseStyle:
    raw = await get_setting(db, SETTING_HOUSE_STYLE, None)
    try:
        return HouseStyle.model_validate(raw) if raw is not None else HouseStyle()
    except ValidationError:
        return HouseStyle()


async def checked_house_style(db: DB, raw: Any) -> HouseStyle:
    """A house style sent by the client (Settings → Label style, or its draft in a preview)."""
    try:
        style = HouseStyle.model_validate(raw)
    except ValidationError as exc:
        raise ApiError("CONFIG_INVALID") from exc
    if style.font not in await get_setting(db, SETTING_FONTS, ALL_FONTS):
        raise ApiError("CONFIG_INVALID")
    return style


@router.get("/label-style", response_model=HouseStyle)
async def read_label_style(_: AnyUser, db: DB) -> HouseStyle:
    return await house_style(db)


@router.put("/label-style", response_model=HouseStyle)
async def write_label_style(body: dict[str, Any], user: Admin, db: DB) -> HouseStyle:
    style = await checked_house_style(db, body)
    row = await db.get(AppSetting, SETTING_HOUSE_STYLE)
    before = (await house_style(db)).model_dump()
    if row is None:
        db.add(AppSetting(key=SETTING_HOUSE_STYLE, value=style.model_dump(), updated_by=user.id))
    else:
        row.value = style.model_dump()
        row.updated_by = user.id
    audit(db, user.id, "setting.update", "app_setting", SETTING_HOUSE_STYLE, before, style.model_dump())
    await db.commit()
    return style
