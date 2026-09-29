"""Canvas geometry (spec 7.1). Inches in, dots out; nothing else mixes the two."""

from __future__ import annotations

import hashlib
import io
import math
from dataclasses import dataclass
from decimal import Decimal

from PIL import Image

SAFE_MARGIN_DOTS = 13


@dataclass(frozen=True)
class CanvasSpec:
    width_dots: int
    height_dots: int
    dpi: int


def canvas_for(width_in: Decimal, height_in: Decimal, print_width_in: Decimal, dpi: int) -> CanvasSpec:
    """W = floor(min(width_in, print_width_in) × dpi); H = floor(height_in × dpi)."""
    width = math.floor(min(Decimal(width_in), Decimal(print_width_in)) * dpi)
    height = math.floor(Decimal(height_in) * dpi)
    return CanvasSpec(width, height, dpi)


def new_canvas(spec: CanvasSpec) -> Image.Image:
    return Image.new("1", (spec.width_dots, spec.height_dots), 1)


def png_bytes(img: Image.Image) -> bytes:
    """Deterministic PNG: no metadata, fixed compression."""
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False, compress_level=9)
    return buf.getvalue()


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()
