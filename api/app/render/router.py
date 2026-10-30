"""POST /render/preview (section 6, 7.7). Never allocates serials."""

from __future__ import annotations

import base64
import uuid
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.auth.deps import DB, AnyUser
from app.configs.effective import current_default, effective_config
from app.configs.resolve import resolve_label_type
from app.configs.router import DraftConfig, checked_spec
from app.errors import ApiError
from app.models import LabelConfig, LabelType, Part
from app.render.service import ConfigLike, preview_serial, render_context, render_part, render_quick
from app.settings.router import checked_house_style
from app.timeutil import local_today, request_zone

router = APIRouter(prefix="/render", tags=["render"])


class PreviewIn(BaseModel):
    part_id: uuid.UUID | None = None  # omitted for a quick label type (v1.1 D24)
    label_type_id: uuid.UUID | None = None
    config_id: uuid.UUID | None = None
    config: DraftConfig | None = None
    manual_values: dict[str, Any] | None = None
    house_style: dict[str, Any] | None = None  # an unsaved Settings → Label style draft (Admin only)
    print_as: uuid.UUID | None = None  # the browser's "Print as" choice, when label_type_id is omitted


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
    layout_box: list[int]  # x, y, w, h in dots: where the design's rows and boxes are drawn


@router.post("/preview", response_model=PreviewOut)
async def preview(body: PreviewIn, request: Request, user: AnyUser, db: DB) -> PreviewOut:
    house = None
    if body.house_style is not None:
        if not user.is_admin:
            raise ApiError("FORBIDDEN")
        house = await checked_house_style(db, body.house_style)
    quick = await db.get(LabelType, body.label_type_id) if body.label_type_id else None
    if quick is not None and quick.kind != "quick":
        quick = None
    part = await db.get(Part, body.part_id) if body.part_id else None
    if part is None and quick is None:
        raise ApiError("NOT_FOUND")
    if body.config is not None:
        await checked_spec(db, body.config.spec, body.config.qr_mode, body.config.serial_mode)
        cfg = ConfigLike(body.config.label_size_id, body.config.spec, body.config.qr_mode, body.config.serial_mode,
                         body.label_type_id)
    else:
        if quick is not None:
            stored = await db.get(LabelConfig, body.config_id) if body.config_id else await current_default(db, quick.id)
        else:
            assert part is not None
            type_id = body.label_type_id or (await resolve_label_type(db, part.id, body.print_as))[0].id
            stored = (await db.get(LabelConfig, body.config_id) if body.config_id
                      else await effective_config(db, part.id, type_id))
        if stored is None:
            raise ApiError("NOT_FOUND")
        cfg = ConfigLike(stored.label_size_id, stored.spec, stored.qr_mode, stored.serial_mode, stored.label_type_id)
    ctx = await render_context(db)
    today = local_today(request_zone(request)).isoformat()
    if quick is not None:
        serial = None
        result, _, _, _ = await render_quick(db, ctx, quick, cfg, body.manual_values, today, house)
    else:
        assert part is not None
        serial = preview_serial(ctx.sequence) if cfg.serial_mode == "required" else None
        result, _, _, _ = await render_part(db, ctx, part, cfg, body.manual_values, today, serial, house)
    return PreviewOut(png_base64=base64.b64encode(result.png).decode("ascii"), fits=result.fits,
                      warnings=[WarningOut(code=w.code, field=w.field, message=w.message) for w in result.warnings],
                      width_dots=result.width_dots, height_dots=result.height_dots, dpi=ctx.printer.dpi,
                      family=result.family, serial_placeholder=serial is not None,
                      layout_box=list(result.layout_box))
