"""Test label job (12.13, 8 'Stored payload and test labels')."""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy import select

from app.db import sessionmaker
from app.models import PrintedLabel, PrintJob
from tests.helpers import agent_alive

V = "/api/v1"


async def test_test_label_blocked_until_agent_seen(admin: httpx.AsyncClient, setup_done: dict[str, Any]) -> None:
    r = await admin.post(f"{V}/printers/{setup_done['printer_id']}/test")
    assert r.status_code == 409 and r.json()["error"]["code"] == "AGENT_UNREACHABLE"
    await agent_alive("out_of_media")
    r = await admin.post(f"{V}/printers/{setup_done['printer_id']}/test")
    assert r.json()["error"]["message"] == "The printer is out of labels."


async def test_test_label_job(admin: httpx.AsyncClient, setup_done: dict[str, Any]) -> None:
    await agent_alive()
    r = await admin.post(f"{V}/printers/{setup_done['printer_id']}/test", headers={"X-Timezone": "America/Chicago"})
    assert r.status_code == 200, r.text
    job = r.json()
    assert job["kind"] == "test" and job["status"] == "queued" and job["labels"] == [] and job["request_id"] is None
    async with sessionmaker()() as db:
        row = await db.get(PrintJob, job["id"])
        assert row is not None
        zpl = row.payload_zpl.decode()
        assert zpl.startswith("^XA\n^MNY\n^PW812\n^LL406\n^FO0,0^GFA,41412,41412,102,")  # Large (default) size
        assert (await db.execute(select(PrintedLabel))).first() is None
    assert (await admin.get(f"{V}/jobs/{job['id']}")).json()["status"] == "queued"


async def test_operator_cannot_print_test_label(operator: httpx.AsyncClient, setup_done: dict[str, Any]) -> None:
    await agent_alive()
    r = await operator.post(f"{V}/printers/{setup_done['printer_id']}/test")
    assert r.status_code == 403
