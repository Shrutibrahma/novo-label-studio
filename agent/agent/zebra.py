"""ZebraUsbPrinter: the real path to the ZQ630 Plus over USB (spec 8.2). Written to spec, untested until the
printer arrives — see the hardware checks in README.md.

Printing: OpenPrinter(AGENT_PRINTER_QUEUE) → StartDocPrinter("Smart Labels job <id>", RAW) → StartPagePrinter →
WritePrinter(bytes) → EndPagePrinter → EndDocPrinter → ClosePrinter.
Status: GetPrinter(level 2).Status mapped per 8.2 step 4.
[SPIKE] ~HS readback: the spooler is write-only, so readback opens the usbprint.sys device (Zebra VID 0A5F) directly.
Only used when AGENT_HS_READBACK=1."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

log = logging.getLogger("agent.zebra")

GUID_DEVINTERFACE_USBPRINT = "{28d78fad-5a12-11d1-ae5b-0000f803a8c2}"
ZEBRA_VID = "VID_0A5F"


def _win32print() -> Any:
    try:
        import win32print  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - only on non-Windows hosts
        raise RuntimeError("usb mode needs Windows with pywin32 installed") from exc
    return win32print


def map_status(status: int, win32print: Any) -> str:
    """8.2 step 4, first match wins: OFFLINE, PAPER_OUT, DOOR_OPEN, PAUSED, ERROR, PRINTING; 0 = ready."""
    if status == 0:
        return "ready"
    for bit, word in (
        (win32print.PRINTER_STATUS_OFFLINE, "offline"),
        (win32print.PRINTER_STATUS_PAPER_OUT, "out_of_media"),
        (win32print.PRINTER_STATUS_DOOR_OPEN, "head_open"),
        (win32print.PRINTER_STATUS_PAUSED, "paused"),
        (win32print.PRINTER_STATUS_ERROR, "error"),
        (win32print.PRINTER_STATUS_PRINTING, "printing"),
    ):
        if status & bit:
            return word
    return "unknown"


class ZebraUsbPrinter:
    def __init__(self, queue: str, hs_readback: bool = False) -> None:
        self.name = queue
        self.queue = queue
        self.hs_readback = hs_readback
        self._w = _win32print()

    def status(self) -> str:
        w = self._w
        try:
            h = w.OpenPrinter(self.queue)
        except Exception:
            log.exception("OpenPrinter(%s) failed", self.queue)
            return "offline"
        try:
            info = w.GetPrinter(h, 2)
        finally:
            w.ClosePrinter(h)
        # "Use printer offline" in Windows also means nothing will print.
        if info.get("Attributes", 0) & getattr(w, "PRINTER_ATTRIBUTE_WORK_OFFLINE", 0x400):
            return "offline"
        return map_status(int(info.get("Status", 0)), w)

    def send(self, job_id: str, payload: bytes) -> None:
        w = self._w
        h = w.OpenPrinter(self.queue)
        try:
            w.StartDocPrinter(h, 1, (f"Smart Labels job {job_id}", None, "RAW"))
            try:
                w.StartPagePrinter(h)
                written = w.WritePrinter(h, payload)
                w.EndPagePrinter(h)
            finally:
                w.EndDocPrinter(h)
        finally:
            w.ClosePrinter(h)
        if written != len(payload):
            raise RuntimeError(f"WritePrinter wrote {written} of {len(payload)} bytes")

    def confirm(self, job_id: str, timeout_s: float) -> bool | None:
        """[SPIKE] Poll ~HS until the printer holds no formats and has no labels left in the batch."""
        if not self.hs_readback:
            return None
        deadline = time.monotonic() + timeout_s
        self._wait_spool_empty(deadline)
        while time.monotonic() < deadline:
            try:
                hs = read_hs()
            except Exception:
                log.exception("[SPIKE] ~HS readback failed for job %s", job_id)
                return None
            if hs.get("paper_out") or hs.get("paused") or hs.get("head_up"):
                return False
            if hs.get("frames", 0) >= 2 and hs.get("formats_in_buffer", 0) == 0 and hs.get("labels_remaining", 0) == 0:
                return True
            time.sleep(0.5)
        return False

    def _wait_spool_empty(self, deadline: float) -> None:
        w = self._w
        while time.monotonic() < deadline:
            h = w.OpenPrinter(self.queue)
            try:
                if not w.EnumJobs(h, 0, 999, 1):
                    return
            finally:
                w.ClosePrinter(h)
            time.sleep(0.2)

    def close(self) -> None:
        return None


# ---------------------------------------------------------------- [SPIKE] ~HS over the USB printer device
def zebra_usb_paths() -> list[str]:
    import winreg

    base = rf"SYSTEM\CurrentControlSet\Control\DeviceClasses\{GUID_DEVINTERFACE_USBPRINT}"
    paths: list[str] = []
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
                    paths.append("\\\\?\\" + name[4:])
    except FileNotFoundError:
        pass
    return paths


def _usb_query(cmd: bytes, frames: int, timeout_s: float = 3.0) -> bytes:
    import pywintypes  # type: ignore[import-not-found]
    import win32event  # type: ignore[import-not-found]
    import win32file  # type: ignore[import-not-found]

    handle = None
    for path in zebra_usb_paths():
        try:
            handle = win32file.CreateFile(path, win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                                          win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE, None,
                                          win32file.OPEN_EXISTING, win32file.FILE_FLAG_OVERLAPPED, None)
            break
        except pywintypes.error:
            continue
    if handle is None:
        raise RuntimeError("no Zebra USB printer device could be opened")
    try:
        ov = pywintypes.OVERLAPPED()
        ov.hEvent = win32event.CreateEvent(None, True, False, None)
        win32file.WriteFile(handle, cmd, ov)
        win32file.GetOverlappedResult(handle, ov, True)
        data = b""
        buf = win32file.AllocateReadBuffer(1024)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline and data.count(b"\x03") < frames:
            ov = pywintypes.OVERLAPPED()
            ov.hEvent = win32event.CreateEvent(None, True, False, None)
            win32file.ReadFile(handle, buf, ov)
            wait_ms = max(1, int((deadline - time.monotonic()) * 1000))
            if win32event.WaitForSingleObject(ov.hEvent, wait_ms) == win32event.WAIT_TIMEOUT:
                win32file.CancelIo(handle)
                break
            n = win32file.GetOverlappedResult(handle, ov, False)
            if n:
                data += bytes(buf[:n])
            else:
                time.sleep(0.05)
        return data
    finally:
        handle.Close()


def parse_hs(data: bytes) -> dict[str, Any]:
    """~HS answers three <STX>…<ETX> strings (ZPL II programming guide)."""
    frames = [f.decode("ascii", "replace").split(",") for f in re.findall(rb"\x02(.*?)\x03", data, re.S)]
    out: dict[str, Any] = {"frames": len(frames)}
    if frames and len(frames[0]) >= 6:
        s1 = frames[0]
        out.update(paper_out=s1[1] == "1", paused=s1[2] == "1", formats_in_buffer=int(s1[4] or 0))
    if len(frames) >= 2 and len(frames[1]) >= 9:
        s2 = frames[1]
        out.update(head_up=s2[2] == "1", labels_remaining=int(s2[8] or 0))
    return out


def read_hs() -> dict[str, Any]:
    return parse_hs(_usb_query(b"~HS\r\n", frames=3))
