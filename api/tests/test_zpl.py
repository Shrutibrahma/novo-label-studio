"""Section 16.1 'ZPL tests': ^GFA byte count = bpr × H; decoding the hex back gives the inverted bitmap."""

from __future__ import annotations

import re
from decimal import Decimal

from PIL import Image, ImageDraw

from app.render.canvas import canvas_for, new_canvas, png_bytes
from app.render.zpl import PrinterSettings, apply_offsets, gfa_payload, job_payload, label_zpl, load_bitmap

INVERT = bytes(b ^ 0xFF for b in range(256))
GFA = re.compile(rb"\^GFA,(\d+),(\d+),(\d+),([0-9A-F]+)\^FS")


def sample(width: int, height: int) -> Image.Image:
    img = Image.new("1", (width, height), 1)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, width - 1, height - 1], outline=0)
    d.line([(0, 0), (width - 1, height - 1)], fill=0, width=3)
    d.rectangle([width // 3, height // 3, width // 2, height // 2], fill=0)
    return img


def test_canvas_dots_match_presets() -> None:
    dims = {(w, h): canvas_for(Decimal(w), Decimal(h), Decimal("4.100"), 203) for w, h in
            [("2.00", "1.00"), ("3.00", "2.00"), ("4.00", "2.00"), ("4.00", "6.00"), ("4.40", "2.00")]}
    got = {k: (v.width_dots, v.height_dots) for k, v in dims.items()}
    assert got == {("2.00", "1.00"): (406, 203), ("3.00", "2.00"): (609, 406), ("4.00", "2.00"): (812, 406),
                   ("4.00", "6.00"): (812, 1218), ("4.40", "2.00"): (832, 406)}  # printable width capped at 4.10 in


def test_gfa_byte_count_and_roundtrip() -> None:
    for width, height in [(406, 203), (609, 406), (812, 406), (812, 1218), (13, 7)]:
        img = sample(width, height)
        zpl = label_zpl(img, 1, PrinterSettings())
        m = GFA.search(zpl)
        assert m, zpl[:80]
        n, n2, bpr = int(m[1]), int(m[2]), int(m[3])
        assert bpr == -(-width // 8) and n == n2 == bpr * height
        decoded = bytes.fromhex(m[4].decode())
        assert len(decoded) == n
        # Decoding gives the inverted bitmap, and row padding bits are white (0 in ZPL).
        assert Image.frombytes("1", (width, height), decoded.translate(INVERT)).tobytes() == img.tobytes()
        pad = bpr * 8 - width
        for row in range(height):
            assert decoded[row * bpr + bpr - 1] & ((1 << pad) - 1) == 0


def test_zpl_command_order_and_optional_commands() -> None:
    img = sample(812, 406)
    plain = label_zpl(img, 3, PrinterSettings()).decode().splitlines()
    assert plain[:4] == ["^XA", "^MNY", "^PW812", "^LL406"]
    assert plain[4].startswith("^FO0,0^GFA,") and plain[5:] == ["^PQ3", "^XZ"]
    full = label_zpl(img, 1, PrinterSettings(darkness=7, speed_ips=Decimal("4.0"))).decode().splitlines()
    assert full[0] == "~SD07" and full[1:5] == ["^XA", "^MNY", "^PW812", "^LL406"] and full[5] == "^PR4"
    assert "^LH" not in "".join(full)


def test_offsets_translate_and_clip() -> None:
    img = Image.new("1", (40, 20), 1)
    img.putpixel((0, 0), 0)
    img.putpixel((39, 19), 0)
    shifted = apply_offsets(img, 10, 5)
    assert shifted.size == img.size
    assert shifted.getpixel((10, 5)) == 0 and shifted.getpixel((0, 0)) != 0
    black = sum(1 for x in range(40) for y in range(20) if shifted.getpixel((x, y)) == 0)
    assert black == 1  # the bottom-right pixel moved off the canvas and was clipped
    _, data = gfa_payload(shifted)
    zpl = label_zpl(img, 1, PrinterSettings(offset_x_dots=10, offset_y_dots=5))
    assert data.hex().upper().encode() in zpl


def test_job_payload_concatenates_in_order() -> None:
    a, b = png_bytes(sample(406, 203)), png_bytes(new_canvas(canvas_for(Decimal(2), Decimal(1), Decimal("4.1"), 203)))
    payload = job_payload([(a, 1), (b, 2)], PrinterSettings())
    assert payload == label_zpl(load_bitmap(a), 1, PrinterSettings()) + label_zpl(load_bitmap(b), 2, PrinterSettings())
    assert payload.count(b"^XA") == 2
