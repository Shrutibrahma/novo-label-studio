"""Bundled OFL fonts (spec 7.2). Only these files are ever used, so preview and print match (D4)."""

from __future__ import annotations

import hashlib
import logging
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from app.config import APP_VERSION, get_settings

log = logging.getLogger("app.render.fonts")

FAMILIES: dict[str, dict[int, str]] = {
    "inter": {400: "Inter-Regular.ttf", 600: "Inter-SemiBold.ttf", 700: "Inter-Bold.ttf", 800: "Inter-ExtraBold.ttf"},
    "roboto_condensed": {400: "RobotoCondensed-Regular.ttf", 700: "RobotoCondensed-Bold.ttf"},
    "atkinson": {400: "AtkinsonHyperlegible-Regular.ttf", 700: "AtkinsonHyperlegible-Bold.ttf"},
}
FAMILY_LABELS = {"inter": "Inter", "roboto_condensed": "Roboto Condensed", "atkinson": "Atkinson Hyperlegible"}


def font_dir() -> Path:
    return get_settings().font_dir


def resolve_weight(family: str, weight: int) -> int:
    """Missing weight in a family -> nearest heavier weight (7.2); heaviest if none is heavier."""
    available = sorted(FAMILIES[family])
    heavier = [w for w in available if w >= weight]
    return heavier[0] if heavier else available[-1]


def font_file(family: str, weight: int) -> Path:
    return font_dir() / FAMILIES[family][resolve_weight(family, weight)]


@lru_cache(maxsize=512)
def load_font(family: str, weight: int, size_dots: float) -> ImageFont.FreeTypeFont:
    # BASIC layout: identical glyph placement on every platform (Windows tests, Linux container).
    return ImageFont.truetype(str(font_file(family, weight)), size_dots, layout_engine=ImageFont.Layout.BASIC)


@lru_cache(maxsize=1)
def font_hashes() -> dict[str, str]:
    out: dict[str, str] = {}
    for family in sorted(FAMILIES):
        for weight in sorted(FAMILIES[family]):
            name = FAMILIES[family][weight]
            path = font_dir() / name
            if not path.exists():
                raise RuntimeError(f"bundled font missing: {path}")
            out[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


@lru_cache(maxsize=1)
def renderer_version() -> str:
    """snapshot.generated.renderer_version = app version + sha256 of the concatenated font hashes (7.2)."""
    joined = "".join(font_hashes()[k] for k in sorted(font_hashes()))
    return f"{APP_VERSION}+{hashlib.sha256(joined.encode('ascii')).hexdigest()}"


def record_font_hashes() -> None:
    for name, digest in font_hashes().items():
        log.info("font %s sha256 %s", name, digest)
    log.info("renderer_version %s", renderer_version())
