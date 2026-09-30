"""SimulatedPrinter: stands in for the ZQ630 Plus until the hardware arrives.

Each job's exact ZPL is written to ./agent-output/{job_id}.zpl, with a PNG of every label decoded from that ZPL
next to it ({job_id}-1.png, …), so what the "printer" received can be compared with the preview.

The status can be forced to test the UI's error states, either with the CLI
    uv run labelstudio-agent sim-status out_of_media
or with a local HTTP call to the running agent (127.0.0.1 only):
    POST http://127.0.0.1:9181/status   {"status": "head_open"}      GET the same URL to read it.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agent.printer import STATUSES
from agent.zpl import write_pngs

log = logging.getLogger("agent.simulated")

FORCEABLE = ("ready", "offline", "out_of_media", "head_open", "paused", "error")


class SimulatedPrinter:
    name = "Simulated ZQ630 Plus"

    def __init__(self, output_dir: Path, on_status_change: Callable[[], None] | None = None) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._status = "ready"
        self._lock = threading.Lock()
        self._on_change = on_status_change
        self._server: ThreadingHTTPServer | None = None

    # ---------------------------------------------------------------- Printer
    def status(self) -> str:
        with self._lock:
            return self._status

    def set_status(self, status: str) -> None:
        if status not in STATUSES:
            raise ValueError(f"unknown status {status!r}; use one of {', '.join(FORCEABLE)}")
        with self._lock:
            changed = status != self._status
            self._status = status
        log.info("simulated printer status -> %s", status)
        if changed and self._on_change:
            self._on_change()

    def send(self, job_id: str, payload: bytes) -> None:
        status = self.status()
        if status not in ("ready", "printing"):
            # A real spooler would hold the job; the simulator fails it so the UI's error path can be seen.
            raise RuntimeError(f"Simulated printer is {status}")
        path = self.output_dir / f"{job_id}.zpl"
        path.write_bytes(payload)
        pngs = write_pngs(payload, self.output_dir, job_id)
        log.info("job %s: wrote %s and %d label image(s)", job_id, path, len(pngs))

    def confirm(self, job_id: str, timeout_s: float) -> bool | None:
        return None  # no readback: jobs stay "Sent to printer" (D17)

    def close(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    # ---------------------------------------------------------------- local control endpoint
    def serve_control(self, port: int) -> None:
        printer = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, code: int, body: dict[str, str]) -> None:
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:  # noqa: N802
                if self.path.rstrip("/") != "/status":
                    return self._send(404, {"error": "not found"})
                self._send(200, {"status": printer.status()})

            def do_POST(self) -> None:  # noqa: N802
                if self.path.rstrip("/") != "/status":
                    return self._send(404, {"error": "not found"})
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    status = str(json.loads(self.rfile.read(length) or b"{}").get("status", ""))
                    if status not in FORCEABLE:
                        raise ValueError(f"status must be one of {', '.join(FORCEABLE)}")
                    printer.set_status(status)
                except (ValueError, json.JSONDecodeError) as exc:
                    return self._send(400, {"error": str(exc)})
                self._send(200, {"status": printer.status()})

            def log_message(self, fmt: str, *args: object) -> None:
                log.debug("control: " + fmt, *args)

        self._server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        threading.Thread(target=self._server.serve_forever, name="sim-control", daemon=True).start()
        log.info("simulated printer control on http://127.0.0.1:%d/status", port)
