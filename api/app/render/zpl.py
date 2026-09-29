"""ZPL encoding of a stored 1-bit bitmap (spec 8.1). All geometry here is printer dots."""

from __future__ import annotations

import io
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from PIL import Image

_INVERT = bytes(b ^ 0xFF for b in range(256))


@dataclass(frozen=True)
class PrinterSettings:
    darkness: int | None = None
    speed_ips: Decimal | int | None = None
    offset_x_dots: int = 0
    offset_y_dots: int = 0


def load_bitmap(png: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(png))
    img.load()
    return img if img.mode == "1" else img.convert("1")


def apply_offsets(img: Image.Image, dx: int, dy: int) -> Image.Image:
    """Translate on a new W × H white canvas, clipping what falls outside — never ^LH (8.1)."""
    if dx == 0 and dy == 0:
        return img
    out = Image.new("1", img.size, 1)
    out.paste(img, (dx, dy))
    return out


def gfa_payload(img: Image.Image) -> tuple[int, bytes]:
    """Packed rows, bits inverted (ZPL prints 1 bits; Pillow '1' stores white as 1), padding bits white."""
    width, height = img.size
    bpr = (width + 7) // 8
    raw = img.tobytes()
    if len(raw) != bpr * height:
        raise ValueError("unexpected bitmap packing")
    data = bytearray(raw.translate(_INVERT))
    pad = bpr * 8 - width
    if pad:
        mask = (0xFF << pad) & 0xFF
        for row in range(height):
            data[row * bpr + bpr - 1] &= mask
    return bpr, bytes(data)


def label_zpl(img: Image.Image, copies: int, printer: PrinterSettings) -> bytes:
    shifted = apply_offsets(img, printer.offset_x_dots, printer.offset_y_dots)
    width, height = shifted.size
    bpr, data = gfa_payload(shifted)
    n = len(data)
    lines: list[str] = []
    if printer.darkness is not None:
        lines.append(f"~SD{printer.darkness:02d}")
    lines += ["^XA", "^MNY", f"^PW{width}", f"^LL{height}"]
    if printer.speed_ips is not None:
        lines.append(f"^PR{int(Decimal(printer.speed_ips))}")
    lines += [f"^FO0,0^GFA,{n},{n},{bpr},{data.hex().upper()}^FS", f"^PQ{copies}", "^XZ"]
    return ("\n".join(lines) + "\n").encode("ascii")


def job_payload(labels: Iterable[tuple[bytes, int]], printer: PrinterSettings) -> bytes:
    """A job's payload = its labels' ZPL concatenated in seq_in_job order (8.1)."""
    return b"".join(label_zpl(load_bitmap(png), copies, printer) for png, copies in labels)
