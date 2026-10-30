"""The part page a label's QR code opens (owner's request, 2026-10-30): GET /scan/{part number}[?sn=serial].

Read-only. Needs a sign-in unless Settings → Label style → QR codes allows anyone who scans (qr.scan_public);
on a server that is also limited by ALLOWED_CIDRS."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Cookie, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select

from app.auth.deps import DB
from app.auth.sessions import COOKIE_NAME, CurrentUser, resolve_session
from app.configs.defaults import SETTING_COMPANY
from app.errors import ApiError
from app.models import Asset, CustomFieldDef, IssuedSerial, Part, PartAlias, PrintedLabel
from app.parts.router import asset_path
from app.render.engine import display_value
from app.settings.router import get_setting, qr_settings

router = APIRouter(prefix="/scan", tags=["scan"])

Session = Annotated[str | None, Cookie(alias=COOKIE_NAME)]


class ScanField(BaseModel):
    label: str
    value: str


class ScanSerial(BaseModel):
    value: str
    status: str
    printed_at: datetime | None


class ScanOut(BaseModel):
    company: str
    part_number: str
    part_name: str
    label_name: str | None
    description: str | None
    revision: str | None
    status: str
    fields: list[ScanField]  # custom fields with a value, in Settings order
    aliases: list[str]
    image_url: str | None
    last_printed_at: datetime | None
    serial: ScanSerial | None  # the serial in the QR code, when it belongs to this part
    part_id: str | None  # only for signed-in users ("Open in the app")


async def viewer(request: Request, db: DB, token: str | None) -> CurrentUser | None:
    """The signed-in user, or None when the page is open to anyone who scans; otherwise 401 (sign in first)."""
    if token:
        try:
            user = await resolve_session(db, token)
            request.state.user_id = user.id
            return user
        except ApiError:
            pass
    if (await qr_settings(db)).scan_public:
        return None
    raise ApiError("SESSION_EXPIRED")


async def find_part(db: DB, part_number: str) -> Part:
    part = (await db.execute(
        select(Part).where(Part.part_number_norm == part_number.strip().upper())
        .order_by((Part.status == "active").desc(), Part.updated_at.desc()).limit(1)
    )).scalar_one_or_none()
    if part is None:
        raise ApiError("NOT_FOUND")
    return part


@router.get("/{part_number:path}/image")
async def scan_image(part_number: str, request: Request, db: DB, ls_session: Session = None) -> Response:
    await viewer(request, db, ls_session)
    part = await find_part(db, part_number)
    asset = await db.get(Asset, part.image_asset_id) if part.image_asset_id else None
    path = asset_path(asset.storage_key) if asset else None
    if asset is None or path is None or not path.exists():
        raise ApiError("NOT_FOUND")
    return Response(path.read_bytes(), media_type=asset.mime_type,
                    headers={"Cache-Control": "private, max-age=31536000, immutable", "ETag": asset.sha256.hex()})


@router.get("/serial/{serial}", response_model=ScanOut)
async def scan_serial(serial: str, request: Request, db: DB, ls_session: Session = None) -> ScanOut:
    """A serial QR code ({base}/S/{serial}): the part the serial was issued for, with the serial's status."""
    user = await viewer(request, db, ls_session)
    issued = await db.get(IssuedSerial, serial.strip().upper())
    part = await db.get(Part, issued.part_id) if issued else None
    if part is None:
        raise ApiError("NOT_FOUND")
    return await scan_out(db, part, user, serial)


@router.get("/{part_number:path}", response_model=ScanOut)
async def scan_part(part_number: str, request: Request, db: DB, ls_session: Session = None,
                    sn: str | None = None) -> ScanOut:
    user = await viewer(request, db, ls_session)
    return await scan_out(db, await find_part(db, part_number), user, sn)


async def scan_out(db: DB, part: Part, user: CurrentUser | None, sn: str | None) -> ScanOut:
    defs = (await db.execute(select(CustomFieldDef).order_by(CustomFieldDef.sort_order, CustomFieldDef.label))).scalars()
    data: dict[str, Any] = part.custom_data or {}
    fields = [ScanField(label=d.label, value=display_value(data[d.key])) for d in defs
              if d.key in data and display_value(data[d.key]) != ""]
    aliases = (await db.execute(select(PartAlias).where(PartAlias.part_id == part.id)
                                .order_by(PartAlias.alias))).scalars().all()
    label_name = next((a.alias for a in aliases if a.is_label_name), None)
    asset = await db.get(Asset, part.image_asset_id) if part.image_asset_id else None
    last = (await db.execute(select(func.max(PrintedLabel.created_at)).where(PrintedLabel.part_id == part.id))).scalar()
    serial = None
    if sn:
        issued = await db.get(IssuedSerial, sn.strip().upper())
        if issued is not None and issued.part_id == part.id:
            printed = (await db.execute(select(func.min(PrintedLabel.created_at))
                                        .where(PrintedLabel.serial_value == issued.value))).scalar()
            serial = ScanSerial(value=issued.value, status=issued.status, printed_at=printed)
    return ScanOut(
        company=str(await get_setting(db, SETTING_COMPANY, "")), part_number=part.part_number,
        part_name=part.part_name, label_name=label_name, description=part.description, revision=part.revision,
        status=part.status, fields=fields, aliases=[a.alias for a in aliases if not a.is_label_name],
        image_url=f"/api/v1/scan/{quote(part.part_number, safe='')}/image?v={asset.sha256.hex()[:12]}" if asset else None,
        last_printed_at=last, serial=serial, part_id=str(part.id) if user else None,
    )
