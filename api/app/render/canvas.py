"""Canvas geometry (spec 7.1). Inches in, dots out; nothing else mixes the two."""

from __future__ import annotations

import hashlib
import math
import struct
import zlib
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


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def png_bytes(img: Image.Image) -> bytes:
    """Deterministic 1-bit PNG written with Python's zlib (level 9), independent of the deflate library bundled
    with Pillow — which differs between the Windows and Linux wheels and would change the bytes (and sha256) of
    identical pixels. Grayscale, bit depth 1 (1 = white, like Pillow mode '1'), filter 0 on every row."""
    if img.mode != "1":
        img = img.convert("1")
    width, height = img.size
    bpr = (width + 7) // 8
    raw = img.tobytes()
    rows = b"".join(b"\x00" + raw[r * bpr:(r + 1) * bpr] for r in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 1, 0, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(rows, 9))
            + _chunk(b"IEND", b""))


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()
