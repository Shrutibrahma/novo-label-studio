"""Agent tests: ZPL decoding, the simulated printer, the job loop and status mapping (no network, no printer)."""

from __future__ import annotations

import json
import types
import urllib.request
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image, ImageDraw

from agent.api import ApiClient, Job
from agent.config import AgentConfig
from agent.main import Agent
from agent.simulated import SimulatedPrinter
from agent.zebra import map_status, parse_hs
from agent.zpl import ZplError, decode, write_pngs

INVERT = bytes(b ^ 0xFF for b in range(256))


def encode(img: Image.Image, copies: int = 1) -> bytes:
    """Same encoding as the API (spec 8.1), kept independent so the decoder is tested against the format."""
    w, h = img.size
    bpr = (w + 7) // 8
    data = bytearray(img.tobytes().translate(INVERT))
    pad = bpr * 8 - w
    for r in range(h):
        data[r * bpr + bpr - 1] &= (0xFF << pad) & 0xFF
    n = len(data)
    return (f"^XA\n^MNY\n^PW{w}\n^LL{h}\n^FO0,0^GFA,{n},{n},{bpr},{bytes(data).hex().upper()}^FS\n^PQ{copies}\n^XZ\n"
            ).encode()


def sample(w: int = 406, h: int = 203) -> Image.Image:
    img = Image.new("1", (w, h), 1)
    d = ImageDraw.Draw(img)
    d.rectangle([13, 13, w - 14, h - 14], outline=0, width=2)
    d.line([(13, 13), (w - 14, h - 14)], fill=0, width=3)
    return img


def test_zpl_roundtrip_and_errors() -> None:
    a, b = sample(), sample(812, 406)
    labels = decode(encode(a, 2) + encode(b))
    assert [(x.width_dots, x.height_dots, x.copies) for x in labels] == [(406, 203, 2), (812, 406, 1)]
    assert labels[0].image.tobytes() == a.tobytes() and labels[1].image.tobytes() == b.tobytes()
    with pytest.raises(ZplError):
        decode(b"^XA^PW10^LL10^FO0,0^GFA,4,4,2,00^FS^XZ")  # byte count mismatch
    with pytest.raises(ZplError):
        decode(b"hello")


def test_simulated_printer_writes_files_and_forced_status(tmp_path: Path) -> None:
    changes: list[int] = []
    sim = SimulatedPrinter(tmp_path, on_status_change=lambda: changes.append(1))
    payload = encode(sample()) + encode(sample(609, 406))
    sim.send("job-1", payload)
    assert (tmp_path / "job-1.zpl").read_bytes() == payload
    assert Image.open(tmp_path / "job-1-1.png").size == (406, 203)
    assert Image.open(tmp_path / "job-1-2.png").size == (609, 406)
    sim.set_status("out_of_media")
    assert sim.status() == "out_of_media" and changes == [1]
    with pytest.raises(RuntimeError, match="Simulated printer is out_of_media"):
        sim.send("job-2", payload)
    with pytest.raises(ValueError):
        sim.set_status("on_fire")
    assert sim.confirm("job-1", 1) is None


def test_simulated_control_endpoint(tmp_path: Path) -> None:
    sim = SimulatedPrinter(tmp_path)
    sim.serve_control(0)
    assert sim._server is not None
    port = sim._server.server_address[1]
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/status", data=json.dumps({"status": "head_open"}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as r:
            assert json.loads(r.read()) == {"status": "head_open"}
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/status") as r:
            assert json.loads(r.read()) == {"status": "head_open"}
        assert sim.status() == "head_open"
    finally:
        sim.close()


def test_control_port_is_exclusive(tmp_path: Path) -> None:
    """A second agent must not silently share the control port (SO_REUSEADDR on Windows would allow it)."""
    first = SimulatedPrinter(tmp_path)
    first.serve_control(0)
    assert first._server is not None
    port = first._server.server_address[1]
    try:
        with pytest.raises(OSError):
            SimulatedPrinter(tmp_path / "b").serve_control(port)
    finally:
        first.close()


class FakeApi:
    def __init__(self, jobs: list[Job]) -> None:
        self.jobs = jobs
        self.reports: list[tuple[str, str, str | None]] = []

    def next_job(self) -> Job | None:
        return self.jobs.pop(0) if self.jobs else None

    def report(self, job_id: str, status: str, error: str | None = None) -> None:
        self.reports.append((job_id, status, error))


class FakePrinter:
    name = "fake"

    def __init__(self, fail: Exception | None = None, confirm: bool | None = None) -> None:
        self.fail, self._confirm, self.sent = fail, confirm, []

    def status(self) -> str:
        return "ready"

    def send(self, job_id: str, payload: bytes) -> None:
        if self.fail:
            raise self.fail
        self.sent.append((job_id, payload))

    def confirm(self, job_id: str, timeout_s: float) -> bool | None:
        return self._confirm

    def close(self) -> None:
        pass


def cfg(tmp_path: Path) -> AgentConfig:
    return AgentConfig(api_base_url="https://x/api", token="t", printer_queue="ZQ630 Plus", poll_seconds=0.01,
                       mode="simulated", output_dir=tmp_path, ca_bundle=None, hs_readback=False, log_dir=tmp_path,
                       sim_control_port=0)


def test_job_loop_reports(tmp_path: Path) -> None:
    job = Job(id="j1", printer_id="p", kind="print", payload=b"^XA^XZ")
    api = FakeApi([job])
    printer = FakePrinter()
    agent = Agent(cfg(tmp_path), api, printer)  # type: ignore[arg-type]
    assert agent.poll_once() is True and agent.poll_once() is False
    assert printer.sent == [("j1", b"^XA^XZ")] and api.reports == [("j1", "sent", None)]

    api = FakeApi([job])
    Agent(cfg(tmp_path), api, FakePrinter(fail=OSError("x" * 900))).poll_once()  # type: ignore[arg-type]
    assert api.reports[0][1] == "failed" and len(api.reports[0][2] or "") == 500

    api = FakeApi([job])
    Agent(cfg(tmp_path), api, FakePrinter(confirm=True)).poll_once()  # type: ignore[arg-type]
    assert [r[1] for r in api.reports] == ["sent", "confirmed"]


def test_api_client_protocol() -> None:
    seen: list[tuple[str, str, Any]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.method, req.url.path, req.headers.get("authorization")))
        if req.url.path.endswith("/jobs/next"):
            return httpx.Response(200, json={"id": "j", "printer_id": "p", "kind": "print", "zpl": "^XA^XZ"})
        return httpx.Response(204 if req.method == "GET" else 200, json={})

    client = ApiClient("https://api.test/api", "tok", transport=httpx.MockTransport(handler))
    job = client.next_job()
    assert job is not None and job.payload == b"^XA^XZ"
    client.report("j", "failed", "e" * 800)
    client.heartbeat("ready", {"hostname": "h"})
    assert [s[:2] for s in seen] == [("GET", "/api/v1/agent/jobs/next"), ("POST", "/api/v1/agent/jobs/j/status"),
                                     ("POST", "/api/v1/agent/heartbeat")]
    assert all(s[2] == "Bearer tok" for s in seen)


def test_windows_status_mapping() -> None:
    w = types.SimpleNamespace(PRINTER_STATUS_OFFLINE=0x80, PRINTER_STATUS_PAPER_OUT=0x10, PRINTER_STATUS_DOOR_OPEN=0x400000,
                              PRINTER_STATUS_PAUSED=0x1, PRINTER_STATUS_ERROR=0x2, PRINTER_STATUS_PRINTING=0x400)
    assert map_status(0, w) == "ready"
    assert map_status(0x80 | 0x10, w) == "offline"  # first match wins, in the 8.2 order
    assert map_status(0x10, w) == "out_of_media"
    assert map_status(0x400000, w) == "head_open"
    assert map_status(0x1, w) == "paused"
    assert map_status(0x2, w) == "error"
    assert map_status(0x400, w) == "printing"
    assert map_status(0x8000, w) == "unknown"


def test_parse_hs() -> None:
    data = (b"\x02030,0,0,1218,000,0,0,0,000,0,0,0\x03\r\n"
            b"\x02001,0,1,0,1,2,6,0,00000002,1,000\x03\r\n\x021234,0\x03\r\n")
    hs = parse_hs(data)
    assert hs == {"frames": 3, "paper_out": False, "paused": False, "formats_in_buffer": 0, "head_up": True,
                  "labels_remaining": 2}


def test_write_pngs_cli(tmp_path: Path) -> None:
    f = tmp_path / "x.zpl"
    f.write_bytes(encode(sample()))
    from agent.zpl import cli

    assert cli([str(f)]) == 0
    assert (tmp_path / "x-1.png").exists()
    assert write_pngs(f.read_bytes(), tmp_path / "o", "y")[0].name == "y-1.png"
