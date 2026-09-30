"""Test label (spec 12.13): a border at the safe margin, a 1-inch ruler along the top and left with ticks
every 0.1 in, and the lines "Novo Smart Labels test", "{printer name} · {dpi} dpi", "{loaded size}",
"{date time}", "v{app version}"."""

from __future__ import annotations

from PIL import ImageDraw

from app.render.canvas import SAFE_MARGIN_DOTS, CanvasSpec, new_canvas, png_bytes
from app.render.fonts import load_font

BORDER_DOTS = 2
TICK_MINOR, TICK_HALF, TICK_INCH = 10, 16, 24
TEXT_START_PT, TEXT_MIN_PT = 10.0, 5.0


def render_test_label(spec: CanvasSpec, lines: list[str]) -> bytes:
    img = new_canvas(spec)
    draw = ImageDraw.Draw(img)
    draw.fontmode = "1"
    w, h, dpi = spec.width_dots, spec.height_dots, spec.dpi
    m = SAFE_MARGIN_DOTS

    # Border whose outer edge sits exactly on the safe margin; nothing is drawn inside the margin.
    draw.rectangle([m, m, w - 1 - m, h - 1 - m], outline=0, width=BORDER_DOTS)

    origin = m + BORDER_DOTS
    for i in range(11):  # 0.0 .. 1.0 in
        offset = origin + round(i * dpi / 10)
        length = TICK_INCH if i in (0, 10) else TICK_HALF if i == 5 else TICK_MINOR
        if offset < w - m - BORDER_DOTS:
            draw.line([(offset, origin), (offset, origin + length - 1)], fill=0, width=1)
        if offset < h - m - BORDER_DOTS:
            draw.line([(origin, offset), (origin + length - 1, offset)], fill=0, width=1)

    text_x = origin + TICK_INCH + 8
    text_y = origin + TICK_INCH + 8
    avail_h = h - m - BORDER_DOTS - 4 - text_y
    pt = TEXT_START_PT
    while pt > TEXT_MIN_PT:
        font = load_font("inter", 400, pt * dpi / 72)
        ascent, descent = font.getmetrics()
        if len(lines) * (ascent + descent + 2) <= avail_h:
            break
        pt -= 0.5
    font = load_font("inter", 400, pt * dpi / 72)
    ascent, descent = font.getmetrics()
    y = text_y
    for line in lines:
        draw.text((text_x, y), line, font=font, fill=0, anchor="la")
        y += ascent + descent + 2
    return png_bytes(img)
