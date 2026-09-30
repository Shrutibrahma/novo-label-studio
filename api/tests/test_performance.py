"""Section 15 performance targets at 50,000 parts. Slow, so only run on request:

    RUN_PERF=1 uv run pytest tests/test_performance.py -s

Targets: search_parts p95 < 150 ms; preview render p95 < 300 ms (4 × 6 in); click Print → job queued < 500 ms;
50,000-row XLSX parsed, validated and diffed < 60 s."""

from __future__ import annotations

import io
import logging
import os
import statistics
import time
import uuid
from decimal import Decimal
from typing import Any

import httpx
import openpyxl
import pytest
from sqlalchemy import text

from app.configs.spec import LabelSpec
from app.db import sessionmaker
from app.render.engine import RenderConfig, RenderPrinter, RenderSize, render
from tests.helpers import agent_alive

logging.basicConfig(level=logging.WARNING)
logging.getLogger("app.imports").setLevel(logging.INFO)

pytestmark = pytest.mark.skipif(os.environ.get("RUN_PERF") != "1", reason="performance run: set RUN_PERF=1")

V = "/api/v1"
N = 50_000


def p95(samples: list[float]) -> float:
    return statistics.quantiles(samples, n=20)[-1]


def report(name: str, value: float, target: float, unit: str) -> None:
    print(f"\n  {name:34} {value:9.1f} {unit}   (target < {target} {unit})")


async def seed() -> None:
    async with sessionmaker()() as db:
        uid = (await db.execute(text("SELECT id FROM app_user LIMIT 1"))).scalar_one()
        await db.execute(text(
            "INSERT INTO part (part_number, part_name, description, revision, created_by, updated_by) "
            "SELECT 'NP-' || lpad(g::text, 6, '0'), "
            "       (ARRAY['Bearing','Shaft','Collar','Bracket','Screw','Washer','Nut','Sensor'])[1 + g % 8] || ' ' || g, "
            "       'Description for part ' || g, chr(65 + g % 5), :u, :u FROM generate_series(1, :n) g"), {"u": uid, "n": N})
        await db.execute(text(
            "INSERT INTO part_alias (part_id, alias, is_label_name, created_by) "
            "SELECT id, 'M' || (row_number() OVER ()) || ' x ' || (row_number() OVER () % 40) || ' alias', true, :u "
            "FROM part WHERE part_number_norm LIKE '%0'"), {"u": uid})
        await db.commit()
        await db.execute(text("ANALYZE"))
        await db.commit()  # planner statistics are transactional: without this they'd be rolled back


class Timer:
    def __init__(self, samples: list[float]) -> None:
        self.samples = samples

    def __enter__(self) -> None:
        self.t = time.perf_counter()

    def __exit__(self, *_: Any) -> None:
        self.samples.append((time.perf_counter() - self.t) * 1000)


QUERIES = ["NP-0421", "bearing", "10 x 3", "M123 x", "NP-04", "shaft 12", "washer", "NP-049999", "sensor 7", "collar",
           "NP-1", "description"]


async def test_search_p95(admin: httpx.AsyncClient, setup_done: dict[str, Any]) -> None:
    await seed()
    samples: list[float] = []
    async with sessionmaker()() as db:
        for q in QUERIES:  # warm-up
            await db.execute(text("SELECT * FROM search_parts(:q, 50)"), {"q": q})
        for _ in range(5):
            for q in QUERIES:
                with Timer(samples):
                    await db.execute(text("SELECT * FROM search_parts(:q, 50)"), {"q": q})
    report("search_parts p95", p95(samples), 150, "ms")
    api_samples: list[float] = []
    for q in QUERIES * 2:
        with Timer(api_samples):
            assert (await admin.get(f"{V}/parts", params={"q": q})).status_code == 200
    report("GET /parts?q= p95 (info)", p95(api_samples), 150, "ms")
    assert p95(samples) < 150


def test_render_p95() -> None:
    spec = LabelSpec.model_validate({"fields": [
        {"key": "label_name", "role": "primary", "uppercase": True, "caption": None},
        {"key": "part_number", "role": "secondary", "uppercase": True, "caption": "PN"},
        {"key": "serial", "role": "secondary", "uppercase": True, "caption": None},
        {"key": "description", "role": "detail", "uppercase": False, "caption": None},
        {"key": "revision", "role": "detail", "uppercase": True, "caption": "REV"}], "manual_fields": [], "style": {}})
    samples: list[float] = []
    for i in range(30):  # a different part each time, like previews while browsing
        snap = {"part": {"label_name": f"Heavy duty flanged bearing housing {i}", "part_number": f"NP-{i:06d}",
                         "description": f"Cast iron pillow block housing {i}", "revision": "C"}, "manual": {},
                "generated": {"serial": "NOVO-88888888", "qr_payload": f"SN:NOVO-88888888|PN:NP-{i:06d}"}}
        with Timer(samples):
            render(snap, RenderConfig(spec, "serial", {}), RenderSize(Decimal("4"), Decimal("6")),
                   RenderPrinter(203, Decimal("4.1")))
    report("render 4x6 p95", p95(samples), 300, "ms")
    assert p95(samples) < 300


async def test_print_to_queued(admin: httpx.AsyncClient, setup_done: dict[str, Any]) -> None:
    await seed()
    await agent_alive()
    part_id = (await admin.get(f"{V}/parts", params={"q": "NP-000100"})).json()["items"][0]["id"]
    samples: list[float] = []
    for _ in range(12):
        with Timer(samples):
            r = await admin.post(f"{V}/print", json={"items": [{"part_id": part_id}], "loaded_size_confirmed": True},
                                 headers={"Idempotency-Key": str(uuid.uuid4())})
        assert r.status_code == 200 and r.json()["jobs"][0]["status"] == "queued", r.text
    report("print→queued p95", p95(samples[2:]), 500, "ms")
    assert p95(samples[2:]) < 500


async def test_import_50k_rows(admin: httpx.AsyncClient, setup_done: dict[str, Any]) -> None:
    await seed()
    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet("Parts")
    ws.append(["Part No", "Name", "Description", "Rev"])
    for i in range(1, N + 1):
        number = f"NP-{i:06d}" if i % 2 else f"NEW-{i:06d}"
        ws.append([number, f"Imported {i}", f"Imported description {i}", "D" if i % 3 == 0 else "A"])
    buf = io.BytesIO()
    wb.save(buf)
    from tests.test_imports import map_and_stage, settle

    started = time.perf_counter()
    r = await admin.post(f"{V}/imports", files={"file": ("big.xlsx", buf.getvalue(), "application/octet-stream")})
    batch = await settle(admin, r.json()["id"])
    staged = await map_and_stage(admin, batch)
    elapsed = time.perf_counter() - started
    report("import 50k rows (parse+validate+diff)", elapsed, 60, "s")
    assert staged["counts"]["total_rows"] == N
    assert elapsed < 60
