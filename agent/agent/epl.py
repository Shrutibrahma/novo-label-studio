"""EPL2 output for printers that print our labels in EPL rather than ZPL (verified on an ARKSCAN 2054A with the
"Zebra LP2844" Seagull driver: ZPL was ignored, EPL GW graphics printed pixel-exact).

The API always sends ZPL (one ^GFA bitmap per label, spec 8.1). With AGENT_PRINTER_LANGUAGE=epl the agent decodes
that ZPL back into the same bitmaps and re-wraps them as EPL, so label design, preview and print history are
unchanged: only the bytes on the wire differ.
"""

from __future__ import annotations

import re

from agent.zpl import decode

_SD = re.compile(rb"~SD(\d{1,2})")
GAP_DOTS = 24  # 3 mm at 203 dpi; the printer's own gap sensing (calibration) finds the real gap


def density_from_darkness(darkness: int) -> int:
    """ZPL ~SD (0–30) → EPL D (0–15)."""
    return max(0, min(15, round(darkness * 15 / 30)))


def zpl_to_epl(zpl: bytes) -> bytes:
    """Every label of the job as EPL: N (clear), optional D (density), q (width), Q (length, gap), GW (the bitmap),
    P (copies). Offsets are already baked into the bitmap by the API, so none are sent here."""
    sd = _SD.search(zpl)
    out = bytearray()
    for label in decode(zpl):
        img = label.image
        width, height = img.size
        bpr = (width + 7) // 8
        data = bytearray(img.tobytes())  # mode "1": 1 = white, 0 = black, which is exactly EPL GW's convention
        pad = bpr * 8 - width
        if pad:  # Pillow pads rows with 0 bits; in EPL those would print black, so make them white
            fill = (1 << pad) - 1
            for row in range(height):
                data[row * bpr + bpr - 1] |= fill
        out += b"\r\nN\r\n"
        if sd:
            out += f"D{density_from_darkness(int(sd[1]))}\r\n".encode()
        out += f"q{bpr * 8}\r\nQ{height},{GAP_DOTS}\r\nGW0,0,{bpr},{height},".encode()
        out += bytes(data)
        out += f"\r\nP{label.copies}\r\n".encode()
    return bytes(out)
