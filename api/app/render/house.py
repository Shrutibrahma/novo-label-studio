"""House label style (v1.1 D21): one company-wide frame, title band and footer drawn around every label type, in
one font. The style used is stored in each snapshot (generated.house_style), so a label always re-renders exactly
as it was printed; snapshots without it (printed before v1.1) render as in v1.

All geometry here is in printer dots at 203 dpi, scaled by dpi / 203 and rounded for other resolutions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from PIL import ImageDraw
from pydantic import BaseModel, ConfigDict

from app.render.fonts import load_font

COMPACT_MAX_IN = 1.5  # labels under 1.5 in tall show the frame only
FRAME = 4
INSET = 4  # text layouts keep this gap from the frame, band and footer; box layouts merge into them
BAND = 34
BAND_PAD = 8
BAND_GAP = 24  # least space between the title and the company name
TITLE_PT = 10.0
TITLE_MIN_PT = 7.0
COMPANY_PT = 7.0
FOOTER_RULE = 2
FOOTER_PT = 7.0
FOOTER_EXTRA = 6
FOOTER_PAD = 8
STEP_PT = 0.5
TITLE_MAX = 24


class HouseStyle(BaseModel):
    """app_setting `label.house_style`."""

    model_config = ConfigDict(extra="forbid")

    font: Literal["inter", "roboto_condensed", "atkinson"] = "inter"
    frame: bool = True
    title_band: bool = True
    company_in_band: bool = True
    footer: bool = True


def snapshot_style(style: HouseStyle, title: str, company: str) -> dict[str, Any]:
    """generated.house_style: the full style used, the title printed in the band and the company name."""
    return style.model_dump() | {"title": title, "company": company}


@dataclass(frozen=True)
class HouseBoxes:
    """`layout` is where a text layout (lines) draws, 4 dots clear of the frame, band and footer. `grid` is where
    box layouts (grid, bin) draw: grown by the box rule width on every side that meets the frame, band or footer
    rule, so box outlines merge into them instead of doubling."""

    layout: tuple[int, int, int, int]
    grid: tuple[int, int, int, int]
    # What was drawn, in dots (for the uniformity test): frame width (0 = none), and the title band and footer
    # rule as (top, height), None when not drawn.
    frame: int = 0
    band: tuple[int, int] | None = None
    footer_rule: tuple[int, int] | None = None


def _scale(v: float, dpi: int) -> int:
    return int(round(v * dpi / 203))


def _dots(pt: float, dpi: int) -> float:
    return pt * dpi / 72


def _width(family: str, weight: int, pt: float, dpi: int, text: str) -> int:
    if not text:
        return 0
    font = load_font(family, weight, _dots(pt, dpi))
    return max(int(round(font.getlength(text))), int(font.getbbox(text, anchor="la")[2]))


def is_compact(height_dots: int, dpi: int) -> bool:
    return height_dots < COMPACT_MAX_IN * dpi


def fit_title(title: str, family: str, dpi: int, room: int) -> tuple[float, str]:
    """Shrinks in 0.5 pt steps from 10 pt down to 7 pt; if it still doesn't fit, drops characters at 7 pt."""
    pt = TITLE_PT
    while pt >= TITLE_MIN_PT:
        if _width(family, 700, pt, dpi, title) <= room:
            return pt, title
        pt -= STEP_PT
    text = title
    while text and _width(family, 700, TITLE_MIN_PT, dpi, text) > room:
        text = text[:-1].rstrip()
    return TITLE_MIN_PT, text


def _text_centered(draw: ImageDraw.ImageDraw, x: int, y: int, h: int, text: str, family: str, weight: int,
                   pt: float, dpi: int, fill: int) -> None:
    """Draws `text` with its capital height centred in the band from y to y + h."""
    font = load_font(family, weight, _dots(pt, dpi))
    top, bottom = font.getbbox("H", anchor="ls")[1], 0
    cap = bottom - top
    baseline = y + (h - cap) // 2 + cap
    draw.text((x, baseline), text, font=font, fill=fill, anchor="ls")


def draw_house(draw: ImageDraw.ImageDraw, hs: dict[str, Any], box: tuple[int, int, int, int], dpi: int,
               compact: bool, serial: str | None, print_date: str | None, rule: int) -> HouseBoxes:
    """Draws the frame, title band and footer inside `box` (the content box inside the safe margin) and returns
    the box left for the layout. `serial` / `print_date` are None when the design already prints them."""
    family = str(hs.get("font") or "inter")
    x, y, w, h = box
    grow_top = grow_bottom = grow_sides = 0
    drawn: dict[str, Any] = {}
    if hs.get("frame", True):
        f = _scale(FRAME, dpi)
        draw.rectangle([x, y, x + w - 1, y + h - 1], outline=0, width=f)
        x, y, w, h = x + f, y + f, w - 2 * f, h - 2 * f
        grow_top = grow_bottom = grow_sides = rule
        drawn["frame"] = f
    if compact:
        return _boxes((x, y, w, h), grow_top, grow_bottom, grow_sides, dpi, drawn)

    if hs.get("title_band", True):
        band = _scale(BAND, dpi)
        draw.rectangle([x, y, x + w - 1, y + band - 1], fill=0)
        pad = _scale(BAND_PAD, dpi)
        title = str(hs.get("title") or "").strip().upper()
        company = str(hs.get("company") or "").strip().upper() if hs.get("company_in_band", True) else ""
        title_w = _width(family, 700, TITLE_PT, dpi, title)
        company_w = _width(family, 400, COMPANY_PT, dpi, company)
        if company and 2 * pad + title_w + _scale(BAND_GAP, dpi) + company_w > w:
            company = ""  # never truncated: left out when it doesn't fit
        if company:
            _text_centered(draw, x + w - pad - company_w, y, band, company, family, 400, COMPANY_PT, dpi, 1)
        if title:
            pt, shown = fit_title(title, family, dpi, w - 2 * pad)
            if shown:
                _text_centered(draw, x + pad, y, band, shown, family, 700, pt, dpi, 1)
        drawn["band"] = (y, band)
        y, h = y + band, h - band
        grow_top = rule

    serial = (serial or "").strip()
    print_date = (print_date or "").strip()
    if hs.get("footer", True) and (serial or print_date):
        font = load_font(family, 400, _dots(FOOTER_PT, dpi))
        a, d = font.getmetrics()
        line_h = a + d + _scale(FOOTER_EXTRA, dpi)
        rule_h = _scale(FOOTER_RULE, dpi)
        top = y + h - line_h - rule_h
        draw.rectangle([x, top, x + w - 1, top + rule_h - 1], fill=0)
        drawn["footer_rule"] = (top, rule_h)
        pad = _scale(FOOTER_PAD, dpi)
        ty = top + rule_h + (line_h - (a + d)) // 2
        if serial:
            draw.text((x + pad, ty), serial, font=font, fill=0, anchor="la")
        if print_date:
            dw = _width(family, 400, FOOTER_PT, dpi, print_date)
            draw.text((x + w - pad - dw, ty), print_date, font=font, fill=0, anchor="la")
        h = top - y
        grow_bottom = min(rule, rule_h)
    return _boxes((x, y, w, h), grow_top, grow_bottom, grow_sides, dpi, drawn)


def _boxes(box: tuple[int, int, int, int], top: int, bottom: int, sides: int, dpi: int,
           drawn: dict[str, Any]) -> HouseBoxes:
    i = _scale(INSET, dpi)
    x, y, w, h = box
    return HouseBoxes((x + i, y + i, w - 2 * i, h - 2 * i), _grow(box, top, bottom, sides), **drawn)


def _grow(box: tuple[int, int, int, int], top: int, bottom: int, sides: int) -> tuple[int, int, int, int]:
    x, y, w, h = box
    return x - sides, y - top, w + 2 * sides, h + top + bottom
