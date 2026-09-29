"""POST /render/preview (section 6, 7.7). Never allocates serials."""

from __future__ import annotations

import base64
import uuid
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.auth.deps import DB, AnyUser
from app.configs.effective import effective_config
from app.configs.router import DraftConfig, checked_spec
from app.errors import ApiError
from app.models import LabelConfig, Part
from app.render.service import ConfigLike, preview_serial, render_context, render_part
from app.timeutil import local_today, request_zone

router = APIRouter(prefix="/render", tags=["render"])


class PreviewIn(BaseModel):
    part_id: uuid.UUID
    config_id: uuid.UUID | None = None
    config: DraftConfig | None = None
    manual_values: dict[str, Any] | None = None


class WarningOut(BaseModel):
    code: str
    field: str | None
    message: str


class PreviewOut(BaseModel):
    png_base64: str
    fits: bool
    warnings: list[WarningOut]
    width_dots: int
    height_dots: int
    dpi: int
    family: str
    serial_placeholder: bool


@router.post("/preview", response_model=PreviewOut)
async def preview(body: PreviewIn, request: Request, _: AnyUser, db: DB) -> PreviewOut:
    part = await db.get(Part, body.part_id)
    if part is None:
        raise ApiError("NOT_FOUND")
    if body.config is not None:
        await checked_spec(db, body.config.spec, body.config.qr_mode, body.config.serial_mode)
        cfg = ConfigLike(body.config.label_size_id, body.config.spec, body.config.qr_mode, body.config.serial_mode)
    else:
        stored = await db.get(LabelConfig, body.config_id) if body.config_id else await effective_config(db, part.id)
        if stored is None:
            raise ApiError("NOT_FOUND")
        cfg = ConfigLike(stored.label_size_id, stored.spec, stored.qr_mode, stored.serial_mode)
    ctx = await render_context(db)
    serial = preview_serial(ctx.sequence) if cfg.serial_mode == "required" else None
    result, _, _, _ = await render_part(db, ctx, part, cfg, body.manual_values,
                                        local_today(request_zone(request)).isoformat(), serial)
    return PreviewOut(png_base64=base64.b64encode(result.png).decode("ascii"), fits=result.fits,
                      warnings=[WarningOut(code=w.code, field=w.field, message=w.message) for w in result.warnings],
                      width_dots=result.width_dots, height_dots=result.height_dots, dpi=ctx.printer.dpi,
                      family=result.family, serial_placeholder=serial is not None)
