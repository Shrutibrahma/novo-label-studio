"""The printer interface the agent drives. Two implementations: ZebraUsbPrinter (real, win32print RAW) and
SimulatedPrinter (files on disk). Selected with AGENT_PRINTER_MODE=simulated|usb."""

from __future__ import annotations

from typing import Protocol

# Printer status words the API accepts (schema.sql printer.last_status).
STATUSES = ("ready", "printing", "offline", "out_of_media", "head_open", "paused", "error", "unknown")


class Printer(Protocol):
    name: str

    def status(self) -> str:
        """One of STATUSES."""
        ...

    def send(self, job_id: str, payload: bytes) -> None:
        """Deliver the job's ZPL exactly as received. Raises on any failure."""
        ...

    def confirm(self, job_id: str, timeout_s: float) -> bool | None:
        """[SPIKE] Wait for the printer to report the labels done. True = confirmed, False = not confirmed,
        None = readback isn't available (the job then stays "sent")."""
        ...

    def close(self) -> None:
        ...
