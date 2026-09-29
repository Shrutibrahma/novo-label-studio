"""M0 hardware spike (spec section 17).

Renders one label to a 1-bit bitmap at 203 dpi, encodes it as ZPL ^GFA, sends it RAW through
the Windows spooler to the ZQ630 Plus, and tests ~HS status readback directly over USB.

  python m0.py render                           # out/label.png + out/label.zpl, encoding self-check
  python m0.py status  --queue "ZQ630 Plus"     # spooler status as the agent would map it (8.2 step 4)
  python m0.py print   --queue "ZQ630 Plus"     # render + send RAW (8.2 step 2)
  python m0.py print   --queue "ZQ630 Plus" --confirm   # ... then poll ~HS until the printer reports done
  python m0.py hs                               # one ~HS readback over the USB printer device
  python m0.py calibrate --queue "ZQ630 Plus"   # ~JC media calibration

Every printer-touching command appends its observations to out/m0_results.jsonl for the decision log.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import segno
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONT_DIR = HERE.parents[1] / "api" / "fonts"
OUT_DIR = HERE / "out"

# ---------------------------------------------------------------- printer profile (spec section 3)
DPI = 203
PRINT_WIDTH_IN = Decimal("4.100")
SAFE_MARGIN = 13  # dots, all four sides
QR_GAP = 16       # dots between QR square and text block

SIZES = {  # name -> (width_in across media, height_in along feed)
    "small": (Decimal("2.00"), Decimal("1.00")),
    "medium": (Decimal("3.00"), Decimal("2.00")),
    "large": (Decimal("4.00"), Decimal("2.00")),
    "tall": (Decimal("4.00"), Decimal("6.00")),
}

# ---------------------------------------------------------------- type (spec 7.3 / 7.5), Inter, emphasis "medium", spacing "standard"
START_PT = {"primary": 20.0, "secondary": 14.0, "detail": 10.0}
MIN_PT = {"primary": 10.0, "secondary": 8.0, "detail": 7.0}
WEIGHT = {"primary": "Bold", "secondary": "SemiBold", "detail": "Regular"}
SPACING = 0.35

SAMPLE = {"part_number": "NP-10421", "part_name": "Bearing Housing", "serial": "NOVO-00000001"}


@lru_cache(maxsize=None)
def font(role: str, pt: float) -> ImageFont.FreeTypeFont:
    path = FONT_DIR / f"Inter-{WEIGHT[role]}.ttf"
    if not path.exists():
        sys.exit(f"Missing font {path}. See spike/m0/README.md, 'Fonts'.")
    return ImageFont.truetype(str(path), pt * DPI / 72)


def line_height(role: str, pt: float) -> int:
    ascent, descent = font(role, pt).getmetrics()
    return ascent + descent


def text_width(role: str, pt: float, text: str) -> int:
    return font(role, pt).getbbox(text, anchor="la")[2]


def block_height(lines: list[tuple[str, str]], sizes: list[float]) -> float:
    h = sum(line_height(r, s) for (r, _), s in zip(lines, sizes))
    h += sum(SPACING * s * DPI / 72 for s in sizes[:-1])
    return h


@dataclass
class RenderResult:
    image: Image.Image
    fits: bool
    warnings: list[str] = field(default_factory=list)
    qr_payload: str | None = None
    qr_module_dots: int | None = None

    @property
    def png(self) -> bytes:
        buf = io.BytesIO()
        self.image.save(buf, format="PNG", optimize=False)
        return buf.getvalue()


def fit_text(lines: list[tuple[str, str]], col_w: int, avail_h: int) -> tuple[list[float], list[str]]:
    """Width pass then height pass (7.5 steps 1, 3, 4). Wrapping (step 2) is out of scope for M0."""
    sizes = [START_PT[r] for r, _ in lines]
    warnings: list[str] = []
    for i, (role, text) in enumerate(lines):
        while text_width(role, sizes[i], text) > col_w and sizes[i] > MIN_PT[role]:
            sizes[i] -= 0.5
    while block_height(lines, sizes) > avail_h and any(s > MIN_PT[r] for (r, _), s in zip(lines, sizes)):
        sizes = [max(MIN_PT[r], s - 0.5) for (r, _), s in zip(lines, sizes)]
    for (role, text), s in zip(lines, sizes):
        if text_width(role, s, text) > col_w:
            warnings.append(f"TEXT_TOO_LONG:{role}")
    if block_height(lines, sizes) > avail_h:
        warnings.append("CONTENT_TOO_TALL")
    return sizes, warnings


def draw_qr(draw: ImageDraw.ImageDraw, payload: str, x0: int, y0: int, side: int) -> tuple[int, list[str]]:
    """7.6: error correction M, no boost, 4-module quiet zone drawn by us, centred in its square."""
    qr = segno.make(payload, error="m", boost_error=False, micro=False)
    modules = qr.symbol_size(border=0)[0]
    m = side // (modules + 8)
    if m < 3:
        return m, ["QR_TOO_SMALL"]
    size = (modules + 8) * m
    ox = x0 + (side - size) // 2 + 4 * m
    oy = y0 + (side - size) // 2 + 4 * m
    for r, row in enumerate(qr.matrix):
        for c, v in enumerate(row):
            if v:
                draw.rectangle([ox + c * m, oy + r * m, ox + (c + 1) * m - 1, oy + (r + 1) * m - 1], fill=0)
    return m, []


def render(size: str, qr_mode: str, values: dict[str, str]) -> RenderResult:
    width_in, height_in = SIZES[size]
    W = math.floor(min(width_in, PRINT_WIDTH_IN) * DPI)
    H = math.floor(height_in * DPI)
    img = Image.new("1", (W, H), 1)
    draw = ImageDraw.Draw(img)
    draw.fontmode = "1"

    cx, cy, cw, ch = SAFE_MARGIN, SAFE_MARGIN, W - 2 * SAFE_MARGIN, H - 2 * SAFE_MARGIN
    warnings: list[str] = []
    payload = None
    module = None

    # Text area defaults to the whole content box (family "stack").
    tx, ty, tw, th = cx, cy, cw, ch
    if qr_mode != "none":
        payload = (f"SN:{values['serial']}|PN:{values['part_number']}" if qr_mode == "serial"
                   else f"PN:{values['part_number']}")
        if len(payload) > 120:
            warnings.append("QR_PAYLOAD_TOO_LONG")
        if H <= 1.5 * W:  # qr_side, QR on the right
            side = math.floor(min(ch, 0.40 * cw))
            qx, qy = cx + cw - side, cy + (ch - side) // 2
            tw = cw - side - QR_GAP
        else:             # qr_top
            side = math.floor(min(0.60 * cw, 0.45 * ch))
            qx, qy = cx + (cw - side) // 2, cy
            ty, th = cy + side + QR_GAP, ch - side - QR_GAP
        module, qr_warn = draw_qr(draw, payload, qx, qy, side)
        warnings += qr_warn

    lines = [("primary", values["part_number"]), ("secondary", values["part_name"])]
    if qr_mode == "serial" or values.get("serial_on"):
        lines.append(("detail", values["serial"]))
    sizes, text_warn = fit_text(lines, tw, th)
    warnings += text_warn

    y = ty + (th - block_height(lines, sizes)) / 2
    for (role, text), s in zip(lines, sizes):
        draw.text((tx, int(y)), text, font=font(role, s), fill=0, anchor="la")
        y += line_height(role, s) + SPACING * s * DPI / 72

    return RenderResult(img, fits=not warnings, warnings=warnings, qr_payload=payload, qr_module_dots=module)


# ---------------------------------------------------------------- ZPL (spec 8.1)
INVERT = bytes(b ^ 0xFF for b in range(256))


def apply_offsets(img: Image.Image, dx: int, dy: int) -> Image.Image:
    if not dx and not dy:
        return img
    out = Image.new("1", img.size, 1)
    out.paste(img, (dx, dy))  # paste clips whatever falls outside the canvas
    return out


def gfa_bytes(img: Image.Image) -> tuple[int, bytes]:
    """Packed rows, inverted (ZPL prints 1 bits; Pillow '1' stores white as 1), padding bits white (0)."""
    W, H = img.size
    bpr = (W + 7) // 8
    raw = img.tobytes()
    assert len(raw) == bpr * H, (len(raw), bpr, H)
    data = bytearray(raw.translate(INVERT))
    pad = bpr * 8 - W
    if pad:
        mask = (0xFF << pad) & 0xFF
        for r in range(H):
            data[r * bpr + bpr - 1] &= mask
    return bpr, bytes(data)


def encode_zpl(img: Image.Image, copies: int = 1, darkness: int | None = None, speed_ips: int | None = None) -> bytes:
    W, H = img.size
    bpr, data = gfa_bytes(img)
    n = len(data)
    lines = []
    if darkness is not None:
        lines.append(f"~SD{darkness:02d}")
    lines += ["^XA", "^MNY", f"^PW{W}", f"^LL{H}"]
    if speed_ips is not None:
        lines.append(f"^PR{speed_ips}")
    lines += [f"^FO0,0^GFA,{n},{n},{bpr},{data.hex().upper()}^FS", f"^PQ{copies}", "^XZ"]
    return ("\n".join(lines) + "\n").encode("ascii")


def check_zpl_roundtrip(img: Image.Image, zpl: bytes) -> None:
    """16.1 ZPL test: byte count = bpr x H, and decoding the hex gives the inverted bitmap."""
    W, H = img.size
    m = re.search(rb"\^GFA,(\d+),(\d+),(\d+),([0-9A-F]+)\^FS", zpl)
    assert m, "no ^GFA field"
    n, n2, bpr = int(m[1]), int(m[2]), int(m[3])
    assert n == n2 == bpr * H and bpr == (W + 7) // 8, (n, n2, bpr, W, H)
    decoded = bytes.fromhex(m[4].decode())
    assert len(decoded) == n
    back = Image.frombytes("1", (W, H), decoded.translate(INVERT))
    # Compare packed bytes, not getdata(): Image.new("1", ..., 1) stores white as 1, decoded images as 255.
    assert back.tobytes() == img.tobytes(), "decoded bitmap differs"
    for r in range(H):  # padding bits must be white (0 after inversion)
        assert decoded[r * bpr + bpr - 1] & ((1 << (bpr * 8 - W)) - 1) == 0, f"row {r} padding not white"


# ---------------------------------------------------------------- Windows spooler (spec 8.2)
def send_raw(queue: str, data: bytes, doc_name: str) -> int:
    import win32print

    h = win32print.OpenPrinter(queue)
    try:
        win32print.StartDocPrinter(h, 1, (doc_name, None, "RAW"))
        try:
            win32print.StartPagePrinter(h)
            written = win32print.WritePrinter(h, data)
            win32print.EndPagePrinter(h)
        finally:
            win32print.EndDocPrinter(h)
    finally:
        win32print.ClosePrinter(h)
    return written


def spooler_status(queue: str) -> dict:
    import win32print

    h = win32print.OpenPrinter(queue)
    try:
        info = win32print.GetPrinter(h, 2)
        jobs = win32print.EnumJobs(h, 0, 999, 1)
    finally:
        win32print.ClosePrinter(h)
    s = info["Status"]
    order = [  # first match wins, in the order listed in 8.2 step 4
        (win32print.PRINTER_STATUS_OFFLINE, "offline"),
        (win32print.PRINTER_STATUS_PAPER_OUT, "out_of_media"),
        (win32print.PRINTER_STATUS_DOOR_OPEN, "head_open"),
        (win32print.PRINTER_STATUS_PAUSED, "paused"),
        (win32print.PRINTER_STATUS_ERROR, "error"),
        (win32print.PRINTER_STATUS_PRINTING, "printing"),
    ]
    mapped = "ready" if s == 0 else next((name for bit, name in order if s & bit), "unknown")
    return {
        "status_raw": s,
        "mapped": mapped,
        "attributes_raw": info["Attributes"],
        "work_offline": bool(info["Attributes"] & win32print.PRINTER_ATTRIBUTE_WORK_OFFLINE),
        "port": info["pPortName"],
        "driver": info["pDriverName"],
        "jobs_in_queue": len(jobs),
    }


def wait_spool_empty(queue: str, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if spooler_status(queue)["jobs_in_queue"] == 0:
            return True
        time.sleep(0.2)
    return False


# ---------------------------------------------------------------- ~HS over the USB printer device (SPIKE)
# The spooler is write-only, so readback opens the usbprint.sys device interface directly.
GUID_DEVINTERFACE_USBPRINT = "{28d78fad-5a12-11d1-ae5b-0000f803a8c2}"
ZEBRA_VID = "VID_0A5F"


def zebra_usb_paths() -> list[str]:
    import winreg

    base = rf"SYSTEM\CurrentControlSet\Control\DeviceClasses\{GUID_DEVINTERFACE_USBPRINT}"
    paths = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as k:
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(k, i)
                except OSError:
                    break
                i += 1
                if ZEBRA_VID in name.upper() and name.startswith("##?#"):
                    paths.append("\\\\?\\" + name[4:])  # "##?#USB#VID_..." -> "\\?\USB#VID_..."
    except FileNotFoundError:
        pass
    return paths  # includes devices seen in the past; open_usb() finds the one that's present


def open_usb():
    import pywintypes
    import win32file

    errors = []
    for path in zebra_usb_paths():
        try:
            h = win32file.CreateFile(
                path, win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE, None,
                win32file.OPEN_EXISTING, win32file.FILE_FLAG_OVERLAPPED, None)
            return h, path
        except pywintypes.error as e:
            errors.append(f"{path}: {e.strerror}")
    raise RuntimeError("No Zebra USB printer device could be opened. " + ("; ".join(errors) or "None registered."))


def usb_query(cmd: bytes, frames_expected: int, timeout_s: float = 3.0) -> bytes:
    import win32event
    import win32file
    import pywintypes

    h, _ = open_usb()
    try:
        ov = pywintypes.OVERLAPPED()
        ov.hEvent = win32event.CreateEvent(None, True, False, None)
        win32file.WriteFile(h, cmd, ov)
        win32file.GetOverlappedResult(h, ov, True)

        data = b""
        deadline = time.monotonic() + timeout_s
        buf = win32file.AllocateReadBuffer(1024)
        while time.monotonic() < deadline and data.count(b"\x03") < frames_expected:
            ov = pywintypes.OVERLAPPED()
            ov.hEvent = win32event.CreateEvent(None, True, False, None)
            win32file.ReadFile(h, buf, ov)
            remaining = max(1, int((deadline - time.monotonic()) * 1000))
            if win32event.WaitForSingleObject(ov.hEvent, remaining) == win32event.WAIT_TIMEOUT:
                win32file.CancelIo(h)
                break
            n = win32file.GetOverlappedResult(h, ov, False)
            if n:
                data += bytes(buf[:n])
            else:
                time.sleep(0.05)  # usbprint may complete reads with 0 bytes while the printer is busy
        return data
    finally:
        h.Close()


def parse_hs(data: bytes) -> dict:
    """~HS answers three <STX>...<ETX> strings (ZPL programming guide, ~HS)."""
    frames = [f.decode("ascii", "replace").split(",") for f in re.findall(rb"\x02(.*?)\x03", data, re.S)]
    out: dict = {"raw": data.decode("ascii", "replace"), "frames": len(frames)}
    if len(frames) >= 1 and len(frames[0]) >= 6:
        s1 = frames[0]
        out.update(paper_out=s1[1] == "1", paused=s1[2] == "1",
                   formats_in_buffer=int(s1[4]), buffer_full=s1[5] == "1")
    if len(frames) >= 2 and len(frames[1]) >= 9:
        s2 = frames[1]
        out.update(head_up=s2[2] == "1", label_waiting=s2[7] == "1", labels_remaining=int(s2[8]))
    return out


def read_hs() -> dict:
    t0 = time.perf_counter()
    result = parse_hs(usb_query(b"~HS\r\n", frames_expected=3))
    result["round_trip_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return result


# ---------------------------------------------------------------- commands
def log_result(kind: str, payload: dict) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    rec = {"at": datetime.now(timezone.utc).isoformat(), "kind": kind, **payload}
    with open(OUT_DIR / "m0_results.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    print(json.dumps(rec, indent=2))


def build(args) -> tuple[RenderResult, bytes]:
    values = dict(SAMPLE, part_number=args.part_number, part_name=args.part_name, serial=args.serial)
    t0 = time.perf_counter()
    res = render(args.size, args.qr, values)
    render_ms = (time.perf_counter() - t0) * 1000
    img = apply_offsets(res.image, args.offset_x, args.offset_y)
    zpl = encode_zpl(img, copies=args.copies, darkness=args.darkness, speed_ips=args.speed)
    check_zpl_roundtrip(img, zpl)

    OUT_DIR.mkdir(exist_ok=True)
    png = res.png
    (OUT_DIR / "label.png").write_bytes(png)
    (OUT_DIR / "label.zpl").write_bytes(zpl)
    print(f"size {args.size}: {img.size[0]} x {img.size[1]} dots, render {render_ms:.1f} ms, "
          f"png sha256 {hashlib.sha256(png).hexdigest()[:16]}…, zpl {len(zpl):,} bytes")
    print(f"qr payload: {res.qr_payload!r}, module {res.qr_module_dots} dots")
    print("fits" if res.fits else f"DOES NOT FIT: {res.warnings}")
    print(f"wrote {OUT_DIR / 'label.png'} and {OUT_DIR / 'label.zpl'}; ZPL round-trip check passed")
    return res, zpl


def cmd_render(args) -> None:
    build(args)


def cmd_print(args) -> None:
    res, zpl = build(args)
    if not res.fits and not args.force:
        sys.exit("Not printing: label doesn't fit (use --force to print anyway).")
    before = spooler_status(args.queue)
    job = f"Label Studio job {uuid.uuid4()}"
    t0 = time.perf_counter()
    written = send_raw(args.queue, zpl, job)
    rec = {"queue": args.queue, "doc": job, "bytes": len(zpl), "written": written,
           "write_ms": round((time.perf_counter() - t0) * 1000, 1), "status_before": before,
           "qr_payload": res.qr_payload, "size": args.size}
    if args.confirm:
        rec["confirm"] = confirm_via_hs(args.queue, args.confirm_timeout)
    log_result("print", rec)


def confirm_via_hs(queue: str, timeout_s: float) -> dict:
    """Wait for the spooler to hand the bytes over, then poll ~HS until the printer reports the batch done."""
    t0 = time.monotonic()
    timeline = []
    if not wait_spool_empty(queue, timeout_s):
        return {"confirmed": False, "reason": "spool job did not complete", "timeline": timeline}
    seen_busy = False
    while time.monotonic() - t0 < timeout_s:
        try:
            hs = read_hs()
        except Exception as e:  # noqa: BLE001 — a spike records every failure mode
            timeline.append({"t": round(time.monotonic() - t0, 2), "error": str(e)[:500]})
            time.sleep(0.5)
            continue
        busy = hs.get("formats_in_buffer", 0) > 0 or hs.get("labels_remaining", 0) > 0
        seen_busy |= busy
        timeline.append({"t": round(time.monotonic() - t0, 2), **{k: v for k, v in hs.items() if k != "raw"}})
        problem = hs.get("paper_out") or hs.get("paused") or hs.get("head_up")
        if hs.get("frames", 0) >= 2 and not busy and not problem:
            return {"confirmed": True, "seen_busy": seen_busy, "timeline": timeline}
        time.sleep(0.5)
    return {"confirmed": False, "reason": "timeout", "seen_busy": seen_busy, "timeline": timeline}


def cmd_status(args) -> None:
    log_result("status", {"queue": args.queue, **spooler_status(args.queue)})


def cmd_hs(args) -> None:
    paths = zebra_usb_paths()
    try:
        log_result("hs", {"usb_paths": paths, **read_hs()})
    except Exception as e:  # noqa: BLE001
        log_result("hs", {"usb_paths": paths, "error": str(e)[:500]})


def cmd_calibrate(args) -> None:
    written = send_raw(args.queue, b"~JC\r\n", "Label Studio calibrate")
    log_result("calibrate", {"queue": args.queue, "written": written})


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def label_opts(sp):
        sp.add_argument("--size", choices=SIZES, default="large")
        sp.add_argument("--qr", choices=["none", "part", "serial"], default="serial")
        sp.add_argument("--part-number", default=SAMPLE["part_number"])
        sp.add_argument("--part-name", default=SAMPLE["part_name"])
        sp.add_argument("--serial", default=SAMPLE["serial"])
        sp.add_argument("--copies", type=int, default=1)
        sp.add_argument("--offset-x", type=int, default=0, help="dots, -200..200")
        sp.add_argument("--offset-y", type=int, default=0, help="dots, -200..200")
        sp.add_argument("--darkness", type=int, choices=range(0, 31), metavar="0-30")
        sp.add_argument("--speed", type=int, help="ips; sends ^PR only when set")

    sp = sub.add_parser("render"); label_opts(sp); sp.set_defaults(fn=cmd_render)
    sp = sub.add_parser("print"); label_opts(sp)
    sp.add_argument("--queue", required=True, help='Windows printer name, e.g. "ZQ630 Plus"')
    sp.add_argument("--force", action="store_true")
    sp.add_argument("--confirm", action="store_true", help="poll ~HS over USB after sending")
    sp.add_argument("--confirm-timeout", type=float, default=30.0)
    sp.set_defaults(fn=cmd_print)
    sp = sub.add_parser("status"); sp.add_argument("--queue", required=True); sp.set_defaults(fn=cmd_status)
    sp = sub.add_parser("hs"); sp.set_defaults(fn=cmd_hs)
    sp = sub.add_parser("calibrate"); sp.add_argument("--queue", required=True); sp.set_defaults(fn=cmd_calibrate)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
