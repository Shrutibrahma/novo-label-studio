"""Label Studio print agent (spec 8.2).

    labelstudio-agent run                  # poll the API and print (mode from AGENT_PRINTER_MODE, default simulated)
    labelstudio-agent sim-status offline   # force the running simulated printer's status (ready, offline, ...)
    labelstudio-agent sim-status           # show it
"""

from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import os
import platform
import signal
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import httpx

from agent import __version__
from agent.api import ApiClient, Job
from agent.config import AgentConfig
from agent.printer import Printer
from agent.simulated import FORCEABLE, SimulatedPrinter

log = logging.getLogger("agent")
CONFIRM_TIMEOUT_S = 30.0


def setup_logging(log_dir: Path) -> Path:
    """%ProgramData%\\LabelStudio\\agent.log, rotating at 10 MB × 5 files (8.2 step 6)."""
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / "agent.log"
        handler: logging.Handler = logging.handlers.RotatingFileHandler(path, maxBytes=10 * 1024 * 1024, backupCount=5,
                                                                        encoding="utf-8")
    except OSError:
        path = Path("agent-output") / "agent.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler.setFormatter(fmt)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root = logging.getLogger()
    root.handlers[:] = [handler, console]
    root.setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return path


def host_info(cfg: AgentConfig, printer: Printer) -> dict[str, str]:
    return {"hostname": socket.gethostname(), "os": platform.platform(), "agent_version": __version__,
            "mode": cfg.mode, "printer": printer.name}


class Agent:
    def __init__(self, cfg: AgentConfig, api: ApiClient, printer: Printer) -> None:
        self.cfg = cfg
        self.api = api
        self.printer = printer
        self.stop = threading.Event()
        self._beat_now = threading.Event()

    def request_heartbeat(self) -> None:
        self._beat_now.set()

    def heartbeat_loop(self) -> None:
        """Every 10 s (and immediately when the simulated status is forced): POST /agent/heartbeat."""
        while not self.stop.is_set():
            try:
                self.api.heartbeat(self.printer.status(), host_info(self.cfg, self.printer))
            except httpx.HTTPError as exc:
                log.warning("heartbeat failed: %s", exc)
            self._beat_now.wait(self.cfg.heartbeat_seconds)
            self._beat_now.clear()

    def handle(self, job: Job) -> None:
        """8.2 steps 2–5. The agent never retries: a failure is reported and the user reprints."""
        log.info("job %s (%s): %d bytes", job.id, job.kind, len(job.payload))
        try:
            self.printer.send(job.id, job.payload)
        except Exception as exc:  # any exception -> failed with its text
            log.exception("job %s failed", job.id)
            self.api.report(job.id, "failed", f"{exc}"[:500] or type(exc).__name__)
            return
        self.api.report(job.id, "sent")
        confirmed = self.printer.confirm(job.id, CONFIRM_TIMEOUT_S)  # [SPIKE] readback, usually None
        if confirmed:
            self.api.report(job.id, "confirmed")

    def poll_once(self) -> bool:
        job = self.api.next_job()
        if job is None:
            return False
        self.handle(job)
        return True

    def run(self) -> None:
        threading.Thread(target=self.heartbeat_loop, name="heartbeat", daemon=True).start()
        log.info("agent %s started: mode=%s printer=%s api=%s", __version__, self.cfg.mode, self.printer.name,
                 self.cfg.api_base_url)
        while not self.stop.is_set():
            try:
                busy = self.poll_once()
            except httpx.HTTPError as exc:
                log.warning("poll failed: %s", exc)
                busy = False
            if not busy:
                self.stop.wait(self.cfg.poll_seconds)


def make_printer(cfg: AgentConfig, agent_ref: list[Agent]) -> Printer:
    if cfg.mode == "usb":
        from agent.zebra import ZebraUsbPrinter

        return ZebraUsbPrinter(cfg.printer_queue, hs_readback=cfg.hs_readback)
    sim = SimulatedPrinter(cfg.output_dir, on_status_change=lambda: agent_ref and agent_ref[0].request_heartbeat())
    sim.serve_control(cfg.sim_control_port)
    return sim


def cmd_run() -> int:
    cfg = AgentConfig.from_env()
    log_path = setup_logging(cfg.log_dir)
    log.info("logging to %s", log_path)
    ref: list[Agent] = []
    printer = make_printer(cfg, ref)
    api = ApiClient(cfg.api_base_url, cfg.token, cfg.ca_bundle)
    agent = Agent(cfg, api, printer)
    ref.append(agent)

    def _stop(*_: object) -> None:
        agent.stop.set()
        agent.request_heartbeat()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    try:
        agent.run()
    finally:
        printer.close()
        api.close()
    return 0


def cmd_sim_status(status: str | None, port: int) -> int:
    url = f"http://127.0.0.1:{port}/status"
    req = urllib.request.Request(url, data=json.dumps({"status": status}).encode() if status else None,
                                 headers={"Content-Type": "application/json"}, method="POST" if status else "GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            print(json.loads(r.read())["status"])
            return 0
    except urllib.error.HTTPError as exc:
        print(json.loads(exc.read()).get("error", str(exc)), file=sys.stderr)
    except urllib.error.URLError:
        print(f"No simulated agent is listening on {url}. Start it with scripts/agent.ps1.", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="labelstudio-agent", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="poll the API and print")
    s = sub.add_parser("sim-status", help="show or force the simulated printer's status")
    s.add_argument("status", nargs="?", choices=FORCEABLE)
    s.add_argument("--port", type=int, default=int(os.environ.get("AGENT_SIM_CONTROL_PORT", "9181")))
    args = p.parse_args(argv)
    if args.cmd == "run":
        return cmd_run()
    return cmd_sim_status(args.status, args.port)


if __name__ == "__main__":
    sys.exit(main())
