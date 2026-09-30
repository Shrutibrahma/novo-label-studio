"""M6: history, label detail, exact reprint (A4), serial lookup and void; operator boundary (A10)."""

from __future__ import annotations

import base64
import uuid
from typing import Any

import httpx
from sqlalchemy import select, text

from app.db import sessionmaker
from app.models import AuditLog, IssuedSerial, PrintedLabel, PrintJob
from tests.helpers import agent_alive
from tests.test_printing import fields, key, ready, size_ids  # noqa: F401  (fixture re-export)

V = "/api/v1"


async def print_one(c: httpx.AsyncClient, part_id: str, **item: Any) -> dict[str, Any]:
    r = await c.post(f"{V}/print", json={"items": [{"part_id": part_id, **item}]}, headers=key())
    assert r.status_code == 200, r.text
    return r.json()


async def label_id_of(job_id: str) -> str:
    async with sessionmaker()() as db:
        return str((await db.execute(select(PrintedLabel.id).where(PrintedLabel.job_id == uuid.UUID(job_id)))).scalars().first())


async def test_history_list_filters_and_detail(admin: httpx.AsyncClient, operator: httpx.AsyncClient, ready: dict[str, Any]) -> None:
    first = await print_one(admin, ready["part"]["id"], group={"total": 2, "start_index": 1})
    await print_one(operator, ready["plain"]["id"], copies=3)
    rows = (await operator.get(f"{V}/history")).json()["items"]
    assert len(rows) == 3 and rows[0]["part_number"] == "NP-2" and rows[0]["copies"] == 3 and rows[0]["by"] == "Olive"
    box = [r for r in rows if r["part_number"] == "NP-10421"]
    assert sorted(r["box"] for r in box) == ["1/2", "2/2"] and box[0]["label_name"] == "10-32 x 1/2 16"
    assert box[0]["size"] == "4 × 2 in" and box[0]["status"] == "queued"
    serial = first["serials"][0]
    assert [r["serial"] for r in (await operator.get(f"{V}/history", params={"q": serial})).json()["items"]] == [serial]
    assert len((await operator.get(f"{V}/history", params={"q": "10-32"})).json()["items"]) == 2
    olive = next(p for p in (await operator.get(f"{V}/history/people")).json() if p["display_name"] == "Olive")
    assert len((await operator.get(f"{V}/history", params={"user_id": olive["id"]})).json()["items"]) == 1

    lid = box[0]["id"]
    d = (await operator.get(f"{V}/labels/{lid}")).json()
    assert d["serial"]["status"] == "allocated" and d["job"]["printer"] == "ZQ630 Plus"
    assert {f["label"]: f["value"] for f in d["fields"]}["Label name"] == "10-32 x 1/2 16"
    assert any(f["value"].startswith("BOX ") for f in d["fields"])
    png = (await operator.get(f"{V}/labels/{lid}/bitmap")).content
    assert base64.b64decode(d["bitmap_png_base64"]) == png

    record = (await operator.get(f"{V}/serials/{serial}")).json()
    assert record["serial"]["value"] == serial and len(record["labels"]) == 1
    assert (await operator.get(f"{V}/serials/NOVO-99999999")).status_code == 404


async def test_a4_reprint_is_exact(admin: httpx.AsyncClient, ready: dict[str, Any], new_client: Any) -> None:
    """A4: the reprinted label is a byte-identical bitmap with the same serial; history shows it under the original."""
    out = await print_one(admin, ready["part"]["id"], copies=2)
    original = await label_id_of(out["jobs"][0]["id"])
    r = await admin.post(f"{V}/labels/{original}/reprint", json={"reason": "damaged"})
    assert r.status_code == 422  # Idempotency-Key required, like every print request
    headers = key()
    r = await admin.post(f"{V}/labels/{original}/reprint", json={"reason": "damaged", "note": "torn corner"}, headers=headers)
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["serials"] == out["serials"] and rep["jobs"][0]["kind"] == "reprint"
    assert (await admin.post(f"{V}/labels/{original}/reprint", json={"reason": "damaged"}, headers=headers)).json()["request_id"] == rep["request_id"]
    async with sessionmaker()() as db:
        a = await db.get(PrintedLabel, uuid.UUID(original))
        b = (await db.execute(select(PrintedLabel).where(PrintedLabel.reprint_of == uuid.UUID(original)))).scalar_one()
        assert a is not None and b.bitmap_png == a.bitmap_png and b.bitmap_sha256 == a.bitmap_sha256
        assert b.snapshot == a.snapshot and b.serial_value == a.serial_value and b.copies == 2
        job = await db.get(PrintJob, b.job_id)
        assert job is not None and job.reprint_reason == "damaged"
        orig_job = await db.get(PrintJob, a.job_id)
        assert orig_job is not None and job.payload_zpl == orig_job.payload_zpl  # same bytes to the printer
    # Reprinting the reprint points back at the original.
    again = await admin.post(f"{V}/labels/{b.id}/reprint", json={"reason": "missing"}, headers=key())
    assert again.status_code == 200
    detail = (await admin.get(f"{V}/labels/{original}")).json()
    assert len(detail["reprints"]) == 2
    only = (await admin.get(f"{V}/history", params={"reprints_only": "true"})).json()["items"]
    assert len(only) == 2 and all(r["reprint_of"] == original for r in only)


async def test_void_serial_blocks_reprint(admin: httpx.AsyncClient, operator: httpx.AsyncClient, ready: dict[str, Any]) -> None:
    out = await print_one(admin, ready["part"]["id"])
    serial = out["serials"][0]
    lid = await label_id_of(out["jobs"][0]["id"])
    assert (await operator.post(f"{V}/serials/{serial}/void", json={"reason": "Wrong part"})).status_code == 403
    r = await admin.post(f"{V}/serials/{serial}/void", json={"reason": "bad"})
    assert r.status_code == 422 and r.json()["error"]["fields"] == {"reason": "Reason must be at least 5 characters."}
    r = await admin.post(f"{V}/serials/{serial}/void", json={"reason": "Label applied to wrong box"})
    assert r.json()["status"] == "voided"
    r = await operator.post(f"{V}/labels/{lid}/reprint", json={"reason": "damaged"}, headers=key())
    assert r.status_code == 409 and r.json()["error"]["message"] == "This serial was voided and can't be reprinted."
    async with sessionmaker()() as db:
        s = await db.get(IssuedSerial, serial)
        assert s is not None and s.void_reason == "Label applied to wrong box"
        assert (await db.execute(select(AuditLog.action).where(AuditLog.action == "serial.void"))).scalar() == "serial.void"


async def test_reprint_rerenders_when_dpi_differs(admin: httpx.AsyncClient, ready: dict[str, Any]) -> None:
    out = await print_one(admin, ready["part"]["id"])
    lid = await label_id_of(out["jobs"][0]["id"])
    async with sessionmaker()() as db:
        await db.execute(text("UPDATE printer SET dpi = 300"))
        await db.commit()
    r = await admin.post(f"{V}/labels/{lid}/reprint", json={"reason": "print_issue"}, headers=key())
    assert r.status_code == 200
    async with sessionmaker()() as db:
        new = (await db.execute(select(PrintedLabel).where(PrintedLabel.reprint_of == uuid.UUID(lid)))).scalar_one()
        old = await db.get(PrintedLabel, uuid.UUID(lid))
        assert old is not None and new.dpi == 300 and new.bitmap_png != old.bitmap_png and new.snapshot == old.snapshot


async def test_a10_operator_cannot_reach_admin_endpoints(admin: httpx.AsyncClient, operator: httpx.AsyncClient,
                                                        ready: dict[str, Any]) -> None:
    """A10: operators can't reach Configure, Settings, Import, or any admin endpoint."""
    part = ready["part"]["id"]
    await agent_alive()
    admin_calls: list[tuple[str, str, Any]] = [
        ("GET", "/users", None), ("POST", "/users", {}), ("PATCH", "/users/x", {}),
        ("PATCH", "/settings", {"company_name": "x"}),
        ("POST", "/sizes", {"name": "x", "width_in": 3, "height_in": 1}), ("PATCH", f"/sizes/{uuid.uuid4()}", {}),
        ("POST", "/custom-fields", {"label": "x", "data_type": "text"}), ("PATCH", "/custom-fields/x", {}),
        ("POST", "/parts", {"part_number": "x", "part_name": "x"}), ("PATCH", f"/parts/{part}", {}),
        ("POST", f"/parts/{part}/archive", None), ("POST", f"/parts/{part}/restore", None),
        ("DELETE", f"/parts/{part}/image", None), ("POST", f"/parts/{part}/aliases", {"alias": "x"}),
        ("PATCH", f"/aliases/{uuid.uuid4()}", {}), ("DELETE", f"/aliases/{uuid.uuid4()}", None),
        ("POST", "/imports", None), ("GET", f"/imports/{uuid.uuid4()}", None),
        ("PUT", f"/imports/{uuid.uuid4()}/mapping", {"mapping": {}}), ("GET", f"/imports/{uuid.uuid4()}/rows", None),
        ("POST", f"/imports/{uuid.uuid4()}/commit", None), ("POST", f"/imports/{uuid.uuid4()}/discard", None),
        ("GET", "/configs", None), ("POST", "/configs", {}), ("DELETE", f"/parts/{part}/config", None),
        ("PATCH", f"/printers/{ready['printer_id']}", {}), ("POST", f"/printers/{ready['printer_id']}/test", None),
        ("POST", f"/printers/{ready['printer_id']}/agent-token", None),
        ("POST", "/serials/NOVO-00000001/void", {"reason": "because"}),
    ]
    for method, path, body in admin_calls:
        r = await operator.request(method, f"{V}{path}", json=body)
        # The role guard runs before body validation, so even malformed bodies get 403.
        assert r.status_code == 403, (method, path, r.status_code, r.text)
