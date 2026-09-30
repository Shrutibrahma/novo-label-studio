"""The label renderer (spec section 7). One pure function produces every label, for preview and print:
render(snapshot, config, size, printer) -> RenderResult. Same inputs always give identical bytes.

All geometry in this module is in printer dots; inches only enter through canvas_for()."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from typing import Any

import segno
from PIL import ImageDraw, ImageFont

from app.configs.spec import LabelSpec, ManualBox, SpecField
from app.errors import message_for
from app.render.canvas import SAFE_MARGIN_DOTS, canvas_for, new_canvas, png_bytes, sha256
from app.render.fonts import load_font

QR_GAP = 16
MAX_QR_PAYLOAD = 120
STEP_PT = 0.5
WRAP_BREAKS = (" ", "-", "/")

# 7.5 start sizes by emphasis, and minimums (points).
START_PT: dict[str, dict[str, float]] = {
    "primary": {"small": 14, "medium": 20, "large": 28},
    "secondary": {"small": 11, "medium": 14, "large": 18},
    "detail": {"small": 9, "medium": 10, "large": 12},
}
MIN_PT = {"primary": 10.0, "secondary": 8.0, "detail": 7.0}
SPACING = {"compact": 0.20, "standard": 0.35, "spacious": 0.55}
PRIMARY_WEIGHT = {"regular": 400, "bold": 700, "extra_bold": 800}


@dataclass(frozen=True)
class RenderConfig:
    spec: LabelSpec
    qr_mode: str  # none | part | serial
    field_labels: dict[str, str]  # field key -> display name for warnings ("Label name", "Max torque", ...)


@dataclass(frozen=True)
class RenderSize:
    width_in: Decimal
    height_in: Decimal


@dataclass(frozen=True)
class RenderPrinter:
    dpi: int
    print_width_in: Decimal


@dataclass(frozen=True)
class Warning:
    code: str
    field: str | None
    message: str


@dataclass
class RenderResult:
    png: bytes
    sha256: bytes
    fits: bool
    warnings: list[Warning]
    width_dots: int
    height_dots: int
    qr_payload: str | None
    family: str


# ---------------------------------------------------------------- values
def display_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def box_text(noun: str, value: Any) -> str:
    """`box_sequence` renders as `BOX 1/3`; without values (preview) as `BOX 1/1` (7.3, 7.7)."""
    index, total = 1, 1
    if isinstance(value, dict):
        index = int(value.get("index", 1))
        total = int(value.get("total", 1))
    return f"{noun} {index}/{total}"


def field_value(f: SpecField, spec: LabelSpec, snapshot: dict[str, Any]) -> str:
    part = snapshot.get("part", {})
    manual = snapshot.get("manual", {})
    generated = snapshot.get("generated", {})
    if f.key in ("serial", "print_date"):
        text = display_value(generated.get(f.key))
    elif f.key.startswith("manual."):
        mkey = f.key[7:]
        mdef = spec.manual(mkey)
        if isinstance(mdef, ManualBox):
            text = box_text(mdef.noun, manual.get(mkey))
        else:
            text = display_value(manual.get(mkey))
    else:
        text = display_value(part.get(f.key))
    return text.upper() if f.uppercase and text else text


# ---------------------------------------------------------------- measuring
@dataclass
class Line:
    field: SpecField
    role: str
    caption: str | None
    text: str
    family: str
    weight: int
    start_pt: float
    min_pt: float
    pt: float = 0.0
    parts: list[str] = field(default_factory=list)  # 1 or 2 visual lines (wrapped)
    too_long: bool = False


def _dots(pt: float, dpi: int) -> float:
    return pt * dpi / 72


def _fonts(line: Line, pt: float, dpi: int) -> tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    size = _dots(pt, dpi)
    return load_font(line.family, line.weight, size), load_font(line.family, 400, size)


@lru_cache(maxsize=16384)
def _advance(family: str, weight: int, size: float, text: str) -> int:
    """Advance width (cheap: no rasterization)."""
    return int(round(load_font(family, weight, size).getlength(text))) if text else 0


@lru_cache(maxsize=16384)
def _exact(family: str, weight: int, size: float, text: str) -> int:
    """Visible width: the larger of the advance and the ink's right edge (rasterizes glyphs, so it's slower)."""
    if not text:
        return 0
    right = load_font(family, weight, size).getbbox(text, anchor="la")[2]
    return max(_advance(family, weight, size, text), int(right))


# Ink never extends more than this fraction of the em past the advance width (true for the bundled fonts),
# so a line whose advance is that far inside the column fits without measuring its ink.
OVERHANG_EM = 0.25


def _caption_width(line: Line, size: float) -> int:
    return _advance(line.family, 400, size, line.caption + " ") if line.caption else 0


def _visual_width(line: Line, text: str, pt: float, dpi: int, with_caption: bool) -> int:
    size = _dots(pt, dpi)
    width = _exact(line.family, line.weight, size, text)
    if with_caption:
        width += _caption_width(line, size)
    return width


def _fits(line: Line, text: str, pt: float, dpi: int, with_caption: bool, col_w: int) -> bool:
    """Same answer as _visual_width(...) <= col_w, measuring the ink only when it can matter."""
    size = _dots(pt, dpi)
    extra = _caption_width(line, size) if with_caption else 0
    adv = _advance(line.family, line.weight, size, text) + extra
    if adv > col_w:
        return False  # visible width >= advance
    if adv + OVERHANG_EM * size <= col_w:
        return True
    return _exact(line.family, line.weight, size, text) + extra <= col_w


def _line_height(line: Line, pt: float, dpi: int) -> int:
    value_font, caption_font = _fonts(line, pt, dpi)
    a1, d1 = value_font.getmetrics()
    if line.caption:
        a2, d2 = caption_font.getmetrics()
        return max(a1, a2) + max(d1, d2)
    return a1 + d1


def _gap(line: Line, pt: float, dpi: int, spacing: float) -> int:
    return int(round(spacing * _dots(pt, dpi)))


def _splits(text: str) -> list[tuple[str, str]]:
    """Two-line splits at word boundaries (space, '-', '/'). A space is dropped; '-' and '/' stay on line 1."""
    out: list[tuple[str, str]] = []
    for i, ch in enumerate(text):
        if ch not in WRAP_BREAKS or i == 0 or i == len(text) - 1:
            continue
        first = text[:i] if ch == " " else text[: i + 1]
        second = text[i + 1:]
        first, second = first.rstrip(), second.lstrip()
        if first and second:
            out.append((first, second))
    return out


def _layout_at(line: Line, pt: float, col_w: int, dpi: int) -> list[str] | None:
    """The visual lines for `line` at `pt`, or None if it can't fit the column at this size."""
    if _fits(line, line.text, pt, dpi, True, col_w):
        return [line.text]
    if line.role == "detail":
        return None  # detail lines never wrap
    best: tuple[int, list[str]] | None = None
    for first, second in _splits(line.text):
        if not (_fits(line, first, pt, dpi, True, col_w) and _fits(line, second, pt, dpi, False, col_w)):
            continue
        w1 = _visual_width(line, first, pt, dpi, True)
        w2 = _visual_width(line, second, pt, dpi, False)
        if w1 <= col_w and w2 <= col_w:
            worst = max(w1, w2)
            if best is None or worst < best[0]:
                best = (worst, [first, second])
    return best[1] if best else None


def _fit_width(line: Line, col_w: int, dpi: int) -> None:
    """7.5 steps 1–2: shrink in 0.5 pt steps to the minimum; if still too wide, wrap onto 2 lines
    (primary/secondary only). Never truncates."""
    pt = line.start_pt
    while pt >= line.min_pt:
        if _fits(line, line.text, pt, dpi, True, col_w):
            line.pt, line.parts = pt, [line.text]
            return
        pt -= STEP_PT
    if line.role != "detail":
        pt = line.start_pt
        while pt >= line.min_pt:
            parts = _layout_at(line, pt, col_w, dpi)
            if parts is not None:
                line.pt, line.parts = pt, parts
                return
            pt -= STEP_PT
    line.pt, line.parts, line.too_long = line.min_pt, [line.text], True


def _block_height(lines: list[Line], dpi: int, spacing: float) -> int:
    total = 0
    for i, line in enumerate(lines):
        h = _line_height(line, line.pt, dpi)
        g = _gap(line, line.pt, dpi, spacing)
        total += h * len(line.parts) + g * (len(line.parts) - 1)
        if i < len(lines) - 1:
            total += g
    return total


def _fit_height(lines: list[Line], col_w: int, avail_h: int, dpi: int, spacing: float) -> bool:
    """7.5 step 3: reduce all sizes together in 0.5 pt steps, never below minimums."""
    while _block_height(lines, dpi, spacing) > avail_h:
        if all(line.pt <= line.min_pt for line in lines):
            return False
        for line in lines:
            if line.pt > line.min_pt:
                line.pt = max(line.min_pt, line.pt - STEP_PT)
            if not line.too_long:
                parts = _layout_at(line, line.pt, col_w, dpi)
                if parts is not None:
                    line.parts = parts
    return True


# ---------------------------------------------------------------- lines from the config
def build_lines(spec: LabelSpec, snapshot: dict[str, Any]) -> list[Line]:
    """Lines in print order: main line, secondary, detail. The primary-role field is the main line; if it is
    empty (or no field has the primary role) the first non-empty field moves up (section 5 rule)."""
    style = spec.style
    values = [(f, field_value(f, spec, snapshot)) for f in spec.fields]
    present = [(f, v) for f, v in values if v]
    if not present:
        return []
    main = next(((f, v) for f, v in present if f.role == "primary"), present[0])
    rest = [(f, v) for f, v in present if f is not main[0]]
    ordered = [(main[0], main[1], "primary")]
    ordered += [(f, v, "secondary") for f, v in rest if f.role == "secondary"]
    ordered += [(f, v, "detail") for f, v in rest if f.role in ("detail", "primary")]
    family = style.font
    lines: list[Line] = []
    for f, text, role in ordered:
        if role == "primary":
            weight = PRIMARY_WEIGHT[style.primary_weight] if family == "inter" else (
                400 if style.primary_weight == "regular" else 700)
        elif role == "secondary":
            weight = 600 if family == "inter" else 700
        else:
            weight = 400
        lines.append(Line(field=f, role=role, caption=f.caption or None, text=text, family=family, weight=weight,
                          start_pt=START_PT[role][style.emphasis], min_pt=MIN_PT[role]))
    return lines


def required_missing(spec: LabelSpec, snapshot: dict[str, Any]) -> list[str]:
    """Required manual fields without a value (box sequences always have one: at least BOX 1/1)."""
    manual = snapshot.get("manual", {})
    return [m.key for m in spec.manual_fields
            if m.required and not isinstance(m, ManualBox) and not display_value(manual.get(m.key))]


# ---------------------------------------------------------------- QR
def _draw_qr(draw: ImageDraw.ImageDraw, payload: str, x0: int, y0: int, side: int) -> str | None:
    """7.6: error correction M, no boost, 4-module quiet zone drawn by us, centred in its square.
    Returns a warning code, or None when drawn."""
    try:
        qr = segno.make(payload, error="m", boost_error=False, micro=False)
    except segno.DataOverflowError:
        return "QR_PAYLOAD_TOO_LONG"
    modules = qr.symbol_size(border=0)[0]
    m = side // (modules + 8)
    if m < 3:
        return "QR_TOO_SMALL"
    size = (modules + 8) * m
    ox = x0 + (side - size) // 2 + 4 * m
    oy = y0 + (side - size) // 2 + 4 * m
    for r, row in enumerate(qr.matrix):
        for c, v in enumerate(row):
            if v:
                draw.rectangle([ox + c * m, oy + r * m, ox + (c + 1) * m - 1, oy + (r + 1) * m - 1], fill=0)
    return None


# ---------------------------------------------------------------- render
def render(snapshot: dict[str, Any], config: RenderConfig, size: RenderSize, printer: RenderPrinter) -> RenderResult:
    spec, style = config.spec, config.spec.style
    canvas = canvas_for(size.width_in, size.height_in, printer.print_width_in, printer.dpi)
    img = new_canvas(canvas)
    draw = ImageDraw.Draw(img)
    draw.fontmode = "1"  # never anti-aliased
    W, H, dpi = canvas.width_dots, canvas.height_dots, canvas.dpi
    m = SAFE_MARGIN_DOTS
    cx, cy, cw, ch = m, m, W - 2 * m, H - 2 * m
    warnings: list[Warning] = []

    def warn(code: str, key: str | None = None) -> None:
        label = config.field_labels.get(key or "")
        if label is None and key and key.startswith("manual."):
            mdef = spec.manual(key[7:])
            label = mdef.label if mdef else key
        label = label or key or ""
        warnings.append(Warning(code, key, message_for(code, Field=label)))

    # 7.4 layout family.
    tx, ty, tw, th = cx, cy, cw, ch
    payload: str | None = None
    family = "stack"
    if config.qr_mode != "none":
        payload = str(snapshot.get("generated", {}).get("qr_payload") or "")
        if H <= W * 3 // 2:
            family = "qr_side"
            side = min(ch, cw * 2 // 5)
            qx = cx if style.qr_position == "left" else cx + cw - side
            qy = cy + (ch - side) // 2
            tw = cw - side - QR_GAP
            tx = cx + side + QR_GAP if style.qr_position == "left" else cx
        else:
            family = "qr_top"
            side = min(cw * 3 // 5, ch * 9 // 20)
            qx, qy = cx + (cw - side) // 2, cy
            ty, th = cy + side + QR_GAP, ch - side - QR_GAP
        if len(payload) > MAX_QR_PAYLOAD or not payload:
            warn("QR_PAYLOAD_TOO_LONG")
        else:
            code = _draw_qr(draw, payload, qx, qy, side)
            if code:
                warn(code)

    for key in required_missing(spec, snapshot):
        warn("REQUIRED_VALUE_MISSING", f"manual.{key}")

    lines = build_lines(spec, snapshot)
    spacing = SPACING[style.spacing]
    tw, th = max(tw, 0), max(th, 0)
    for line in lines:
        _fit_width(line, tw, dpi)
    fits_height = _fit_height(lines, tw, th, dpi, spacing) if lines else True
    for line in lines:
        if line.too_long:
            warn("TEXT_TOO_LONG", line.field.key)
    if not fits_height:
        warn("CONTENT_TOO_TALL")

    # Draw: block vertically centred in its area, each line left or centre aligned.
    y = ty + max(0, (th - _block_height(lines, dpi, spacing)) // 2)
    for i, line in enumerate(lines):
        value_font, caption_font = _fonts(line, line.pt, dpi)
        height = _line_height(line, line.pt, dpi)
        gap = _gap(line, line.pt, dpi, spacing)
        for j, part in enumerate(line.parts):
            with_caption = j == 0 and bool(line.caption)
            width = _visual_width(line, part, line.pt, dpi, with_caption)
            x = tx if style.alignment == "left" else tx + (tw - width) // 2
            if with_caption and line.caption:
                draw.text((x, y), line.caption, font=caption_font, fill=0, anchor="la")
                x += int(round(caption_font.getlength(line.caption + " ")))
            draw.text((x, y), part, font=value_font, fill=0, anchor="la")
            y += height + (gap if j < len(line.parts) - 1 else 0)
        if i < len(lines) - 1:
            y += gap

    png = png_bytes(img)
    return RenderResult(png=png, sha256=sha256(png), fits=not warnings, warnings=warnings, width_dots=W,
                        height_dots=H, qr_payload=payload, family=family)
