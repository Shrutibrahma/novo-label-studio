"""The label renderer (spec section 7). One pure function produces every label, for preview and print:
render(snapshot, config, size, printer) -> RenderResult. Same inputs always give identical bytes.

All geometry in this module is in printer dots; inches only enter through canvas_for()."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from typing import Any

import segno
from PIL import Image, ImageDraw, ImageFont, ImageOps

from app.configs.spec import LabelSpec, ManualBox, SpecField
from app.errors import message_for
from app.render.canvas import SAFE_MARGIN_DOTS, canvas_for, new_canvas, png_bytes, sha256
from app.render.fonts import load_font

QR_GAP = 16
IMAGE_GAP = 16
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


# ---------------------------------------------------------------- picture
def picture_bits(picture: Image.Image, box_w: int, box_h: int) -> Image.Image:
    """The part's picture as 1-bit dots fitting box_w × box_h: flattened onto white, greyscale, contrast
    stretched, scaled to fit (aspect kept) and Floyd–Steinberg dithered, since the printer has no grey."""
    img = picture
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        img = Image.alpha_composite(white, rgba)
    grey = ImageOps.autocontrast(img.convert("L"), cutoff=1)
    fitted = ImageOps.contain(grey, (max(1, box_w), max(1, box_h)), Image.Resampling.LANCZOS)
    return fitted.convert("1", dither=Image.Dither.FLOYDSTEINBERG)


def _place_picture(img: Image.Image, picture: Image.Image, x: int, y: int, w: int, h: int) -> None:
    bits = picture_bits(picture, w, h)
    img.paste(bits, (x + (w - bits.width) // 2, y + (h - bits.height) // 2))



# ---------------------------------------------------------------- bin label grid
MAX_QR_PAYLOAD_DATA = 300  # style.qr_content "label_data": several lines of values
RULE = 2  # grid line width, dots
PAD = 6  # inner padding of a box, dots
HEADING_PT = 6.5
BIN_PT = {  # (start, minimum) points per box kind
    "title": (15.0, 8.0),
    "main": (24.0, 10.0),
    "name": (12.0, 7.0),
    "info": (16.0, 7.0),
}


def value_for_key(key: str, spec: LabelSpec, snapshot: dict[str, Any]) -> str:
    return field_value(SpecField(key=key, role="detail"), spec, snapshot)


def _weights(style: Any) -> tuple[int, int]:
    """(heading weight, value weight) for the chosen font."""
    if style.font == "inter":
        return 600, PRIMARY_WEIGHT[style.primary_weight] if style.primary_weight != "regular" else 600
    return 400, 700


def _fit_box(text: str, family: str, weight: int, start_pt: float, min_pt: float, w: int, h: int,
             dpi: int, wrap: bool) -> tuple[float, list[str]] | None:
    """Largest size (0.5 pt steps) at which `text` fits w × h on one line, or on two when `wrap`."""
    pt = start_pt
    while pt >= min_pt:
        size = _dots(pt, dpi)
        font = load_font(family, weight, size)
        a, d = font.getmetrics()
        if a + d <= h and _exact(family, weight, size, text) <= w:
            return pt, [text]
        if wrap and 2 * (a + d) <= h:
            best: tuple[int, list[str]] | None = None
            for first, second in _splits(text):
                widest = max(_exact(family, weight, size, first), _exact(family, weight, size, second))
                if widest <= w and (best is None or widest < best[0]):
                    best = (widest, [first, second])
            if best:
                return pt, best[1]
        pt -= STEP_PT
    return None


def _draw_lines(draw: ImageDraw.ImageDraw, parts: list[str], family: str, weight: int, pt: float, dpi: int,
                x: int, y: int, w: int, h: int, align: str) -> None:
    size = _dots(pt, dpi)
    font = load_font(family, weight, size)
    a, d = font.getmetrics()
    total = (a + d) * len(parts)
    ty = y + max(0, (h - total) // 2)
    for part in parts:
        width = _exact(family, weight, size, part)
        tx = x if align == "left" else x + max(0, (w - width) // 2)
        draw.text((tx, ty), part, font=font, fill=0, anchor="la")
        ty += a + d


def _rect(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int) -> None:
    draw.rectangle([x, y, x + w - 1, y + h - 1], outline=0, width=RULE)


def _heading(draw: ImageDraw.ImageDraw, text: str, family: str, weight: int, dpi: int, x: int, y: int, w: int
             ) -> int:
    """A small heading strip (white text on a black bar) at the top of a box; returns its height."""
    if not text:
        return 0
    size = _dots(HEADING_PT, dpi)
    font = load_font(family, weight, size)
    a, d = font.getmetrics()
    bar = a + d + 4
    draw.rectangle([x, y, x + w - 1, y + bar - 1], fill=0)
    label = text.upper()
    width = _exact(family, weight, size, label)
    while width > w - 2 * PAD and len(label) > 1:  # headings are short; clip rather than fail
        label = label[:-1]
        width = _exact(family, weight, size, label)
    draw.text((x + (w - width) // 2, y + 2), label, font=font, fill=1, anchor="la")
    return bar


def render_bin(img: Image.Image, draw: ImageDraw.ImageDraw, snapshot: dict[str, Any], config: RenderConfig,
               box: tuple[int, int, int, int], dpi: int, picture: Image.Image | None,
               warn: Any) -> str | None:
    """The bin-label grid inside `box` (x, y, w, h). Returns the QR payload drawn, if any.

    ┌───────────────── title ─────────────────┐
    │ main (big)               │ info1 │ info2 │
    │ name                     │       │       │
    ├── QR ───────┬── picture ──┬── info3 ─────┤
    │             │             ├── info4 ─────┤
    └─────────────┴─────────────┴──────────────┘
    Boxes without a field keep their heading, so every label of a set looks the same."""
    spec, style, layout = config.spec, config.spec.style, config.spec.bin
    family = style.font
    head_w, value_w = _weights(style)
    x0, y0, w, h = box
    _rect(draw, x0, y0, w, h)

    def value(slot: Any) -> str:
        return value_for_key(slot.key, spec, snapshot) if slot.key else ""

    def text_box(slot: Any, kind: str, x: int, y: int, bw: int, bh: int, heading: bool, align: str) -> None:
        _rect(draw, x, y, bw, bh)
        top = _heading(draw, slot.heading or "", family, head_w, dpi, x, y, bw) if heading else 0
        text = value(slot)
        if not text:
            return
        start, minimum = BIN_PT[kind]
        fit = _fit_box(text, family, value_w if kind != "name" else value_w, start, minimum,
                       bw - 2 * PAD, bh - top - 2 * PAD, dpi, wrap=kind in ("name", "main"))
        if fit is None:
            warn("TEXT_TOO_LONG", slot.key)
            fit = (minimum, [text])
        _draw_lines(draw, fit[1], family, value_w, fit[0], dpi, x + PAD, y + top + PAD, bw - 2 * PAD,
                    bh - top - 2 * PAD, align)

    # Title bar.
    y = y0
    if layout.title.strip():
        th = h * 14 // 100
        _rect(draw, x0, y, w, th)
        fit = _fit_box(layout.title.strip(), family, value_w, *BIN_PT["title"], w - 2 * PAD, th - 2 * PAD, dpi,
                       wrap=False)
        if fit:
            _draw_lines(draw, fit[1], family, value_w, fit[0], dpi, x0 + PAD, y + PAD, w - 2 * PAD, th - 2 * PAD,
                        "center")
        y += th

    # Upper block: main value and name on the left (heading in a narrow column), info1/info2 on the right.
    upper = (y0 + h - y) * 42 // 100
    left_w = w * 60 // 100
    side_w = (w - left_w) // 2
    main_h = upper * 52 // 100
    for slot, kind, yy, hh in ((layout.main, "main", y, main_h), (layout.name, "name", y + main_h, upper - main_h)):
        cap_w = left_w * 18 // 100
        _rect(draw, x0, yy, cap_w, hh)
        cap = (slot.heading or "").upper()
        if cap:
            size = _dots(HEADING_PT, dpi)
            font = load_font(family, head_w, size)
            draw.text((x0 + PAD, yy + PAD), cap, font=font, fill=0, anchor="la")
        text_box(slot, kind, x0 + cap_w, yy, left_w - cap_w, hh, heading=False, align="left")
    text_box(layout.info1, "info", x0 + left_w, y, side_w, upper, heading=True, align="center")
    text_box(layout.info2, "info", x0 + left_w + side_w, y, w - left_w - side_w, upper, heading=True,
             align="center")
    y += upper

    # Lower block: QR, picture, and info3/info4 stacked on the right.
    lower = y0 + h - y
    has_qr = config.qr_mode != "none"
    wants_picture = bool(snapshot.get("generated", {}).get("image_sha256")) and style.image_position != "none"
    info_w = w * 34 // 100
    media = [m for m, on in (("qr", has_qr), ("picture", wants_picture)) if on]
    if not media:
        info_w = w
    media_w = (w - info_w) // len(media) if media else 0
    payload: str | None = None
    x = x0
    for m in media:
        bw = media_w if m != media[-1] else w - info_w - (x - x0)
        _rect(draw, x, y, bw, lower)
        top = _heading(draw, layout.qr_heading if m == "qr" else layout.image_heading, family, head_w, dpi, x, y, bw)
        ix, iy, iw, ih = x + PAD, y + top + PAD, bw - 2 * PAD, lower - top - 2 * PAD
        if m == "qr":
            payload = str(snapshot.get("generated", {}).get("qr_payload") or "")
            limit = MAX_QR_PAYLOAD_DATA if style.qr_content == "label_data" else MAX_QR_PAYLOAD
            if not payload or len(payload) > limit:
                warn("QR_PAYLOAD_TOO_LONG")
            else:
                side = min(iw, ih)
                code = _draw_qr(draw, payload, ix + (iw - side) // 2, iy + (ih - side) // 2, side)
                if code:
                    warn(code)
        elif picture is None:
            warn("LABEL_IMAGE_MISSING")
        else:
            _place_picture(img, picture, ix, iy, iw, ih)
        x += bw
    half = lower // 2
    text_box(layout.info3, "info", x, y, x0 + w - x, half, heading=True, align="center")
    text_box(layout.info4, "info", x, y + half, x0 + w - x, lower - half, heading=True, align="center")
    return payload

# ---------------------------------------------------------------- render
def render(snapshot: dict[str, Any], config: RenderConfig, size: RenderSize, printer: RenderPrinter,
           picture: Image.Image | None = None) -> RenderResult:
    """`picture` is the part's image when the snapshot prints one (generated.image_sha256); a snapshot that
    names a picture but gets none renders with a LABEL_IMAGE_MISSING warning, so it can't be printed."""
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

    if style.layout == "bin":
        payload = render_bin(img, draw, snapshot, config, (cx, cy, cw, ch), dpi, picture, warn)
        for key in required_missing(spec, snapshot):
            warn("REQUIRED_VALUE_MISSING", f"manual.{key}")
        png = png_bytes(img)
        return RenderResult(png=png, sha256=sha256(png), fits=not warnings, warnings=warnings, width_dots=W,
                            height_dots=H, qr_payload=payload, family="bin")

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
        limit = MAX_QR_PAYLOAD_DATA if style.qr_content == "label_data" else MAX_QR_PAYLOAD
        if len(payload) > limit or not payload:
            warn("QR_PAYLOAD_TOO_LONG")
        else:
            code = _draw_qr(draw, payload, qx, qy, side)
            if code:
                warn(code)

    # The picture takes a square beside the text (wide labels) or a band above it (tall labels).
    if snapshot.get("generated", {}).get("image_sha256") and style.image_position != "none":
        if picture is None:
            warn("LABEL_IMAGE_MISSING")
        elif H >= W * 5 // 4:  # tall labels (4 × 6 and portrait custom sizes): a band above the text
            band = min(th * 2 // 5, tw)
            _place_picture(img, picture, tx, ty, tw, band)
            ty, th = ty + band + IMAGE_GAP, th - band - IMAGE_GAP
        else:
            side = min(th, tw * 2 // 5)
            ix = tx if style.image_position == "left" else tx + tw - side
            _place_picture(img, picture, ix, ty + (th - side) // 2, side, side)
            if style.image_position == "left":
                tx += side + IMAGE_GAP
            tw -= side + IMAGE_GAP

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
