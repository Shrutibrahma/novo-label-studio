"""Quick labels (v1.1 U4, D24): label types printed without a part."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from alembic import command
from alembic.config import Config
from anyio import to_thread
from sqlalchemy import select, text

from app.db import dispose_engine, init_engine, sessionmaker
from app.models import PrintedLabel
from tests.conftest import API_DIR
from tests.helpers import agent_alive

V = "/api/v1"


async def workstation(admin: httpx.AsyncClient) -> dict[str, Any]:
    r = await admin.post(f"{V}/label-types", json={"name": "Workstation sign", "kind": "quick", "preset": "workstation"})
    assert r.status_code == 201, r.text
    return r.json()


async def quick(c: httpx.AsyncClient, type_id: str, **body: Any) -> httpx.Response:
    return await c.post(f"{V}/print/quick", headers={"Idempotency-Key": str(uuid.uuid4())},
                        json={"label_type_id": type_id, "manual_values": {"station": "CELL 4"}, "copies": 2} | body)


async def test_quick_label_prints_reprints_and_stays_out_of_freshness(
        admin: httpx.AsyncClient, operator: httpx.AsyncClient, setup_done: dict[str, Any]) -> None:
    sign = await workstation(admin)
    assert sign["kind"] == "quick"
    part = (await admin.post(f"{V}/parts", json={"part_number": "P-1", "part_name": "Plain"})).json()
    await admin.patch(f"{V}/printers/{setup_done['printer_id']}", json={"loaded_label_size_id": sign["size"]["id"]})
    await agent_alive()

    # Preview without a part; a missing required value is reported, printing refuses it.
    prev = (await operator.post(f"{V}/render/preview", json={"label_type_id": sign["id"], "manual_values": {}})).json()
    assert [w["code"] for w in prev["warnings"]] == ["REQUIRED_VALUE_MISSING"]
    r = await quick(operator, sign["id"], manual_values={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "REQUIRED_VALUE_MISSING"

    r = await quick(operator, sign["id"])
    assert r.status_code == 200, r.text
    assert r.json()["serials"] == [] and r.json()["jobs"][0]["labels"][0]["part_id"] is None
    async with sessionmaker()() as db:
        label = (await db.execute(select(PrintedLabel))).scalar_one()
    assert label.part_id is None and label.copies == 2 and label.snapshot["part"] is None
    assert label.snapshot["generated"]["quick"] is True and label.snapshot["manual"] == {"station": "CELL 4"}

    # History: listed as a quick label, filterable; reprint is byte-identical.
    rows = (await operator.get(f"{V}/history", params={"quick_only": "true"})).json()["items"]
    assert len(rows) == 1 and rows[0]["quick"] and rows[0]["part_id"] is None and rows[0]["label_type"] == "Workstation sign"
    detail = (await operator.get(f"{V}/labels/{label.id}")).json()
    assert [f["value"] for f in detail["fields"] if f["key"] == "manual.station"] == ["CELL 4"]
    r = await operator.post(f"{V}/labels/{label.id}/reprint", headers={"Idempotency-Key": str(uuid.uuid4())},
                            json={"reason": "damaged"})
    assert r.status_code == 200, r.text
    async with sessionmaker()() as db:
        copies = (await db.execute(select(PrintedLabel).where(PrintedLabel.reprint_of == label.id))).scalar_one()
    assert copies.bitmap_sha256 == label.bitmap_sha256 and copies.part_id is None

    # The part's freshness ignores quick labels; parts never resolve to (or print as) a quick type.
    async with sessionmaker()() as db:
        state = (await db.execute(text("SELECT label_state FROM part_label_freshness WHERE part_id = :p"),
                                  {"p": part["id"]})).scalar_one()
    assert state == "never_printed"
    assert (await operator.get(f"{V}/parts/{part['id']}", params={"print_as": sign["id"]})).json()["label_type"]["reason"] == "first"
    r = await admin.patch(f"{V}/parts/{part['id']}", json={"preferred_label_type_id": sign["id"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "QUICK_LABEL_INVALID"
    r = await operator.post(f"{V}/print", headers={"Idempotency-Key": str(uuid.uuid4())}, json={"items": [
        {"part_id": part["id"], "copies": 1, "quantity": 1, "manual_values": {}, "label_type_id": sign["id"]}]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "QUICK_LABEL_INVALID"
    first = (await admin.get(f"{V}/label-types")).json()[0]
    assert (await quick(operator, first["id"])).json()["error"]["code"] == "QUICK_LABEL_INVALID"


async def test_quick_validation(admin: httpx.AsyncClient) -> None:
    sign = await workstation(admin)
    size = sign["size"]["id"]
    base = {"scope": "default", "label_type_id": sign["id"], "label_size_id": size, "qr_mode": "none",
            "serial_mode": "none"}
    ok = {"fields": [], "manual_fields": [{"key": "t", "label": "T", "type": "text", "max_length": 10}],
          "style": {"layout": "grid"}, "grid": {"rows": [{"cells": [
              {"kind": "field", "key": "manual.t"}, {"kind": "field", "key": "print_date"},
              {"kind": "text", "text": "QC"}, {"kind": "arrow"}, {"kind": "blank", "heading": "BY"}]}]}}
    assert (await admin.post(f"{V}/configs", json=base | {"spec": ok})).status_code == 201

    def with_cell(cell: dict[str, Any]) -> dict[str, Any]:
        return ok | {"grid": {"rows": [{"cells": [cell]}]}}

    bad = [
        base | {"spec": with_cell({"kind": "field", "key": "part_number"})},
        base | {"spec": with_cell({"kind": "image"})},
        base | {"spec": with_cell({"kind": "qr"}), "qr_mode": "part"},
        base | {"spec": ok, "serial_mode": "required"},
        base | {"spec": ok | {"manual_fields": [*ok["manual_fields"],
                                                {"key": "b", "label": "B", "type": "box_sequence", "noun": "BOX"}]}},
    ]
    for body in bad:
        r = await admin.post(f"{V}/configs", json=body)
        assert r.status_code == 422 and r.json()["error"]["code"] == "QUICK_LABEL_INVALID", (body, r.text)
    part = (await admin.post(f"{V}/parts", json={"part_number": "P-9", "part_name": "Nine"})).json()
    r = await admin.post(f"{V}/configs", json=base | {"spec": ok, "scope": "part", "part_id": part["id"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "QUICK_LABEL_INVALID"
    # Kind is fixed at creation; a part preset can't become a quick type.
    r = await admin.post(f"{V}/label-types", json={"name": "Odd", "kind": "quick", "preset": "part"})
    assert r.status_code == 422
    # The last part type can't be archived even when quick types exist.
    first = (await admin.get(f"{V}/label-types")).json()[0]
    assert (await admin.post(f"{V}/label-types/{first['id']}/archive")).status_code == 422
    assert (await admin.post(f"{V}/label-types/{sign['id']}/archive")).status_code == 204


async def test_migration_up_and_down_with_prints(admin: httpx.AsyncClient, setup_done: dict[str, Any],
                                                 migrated: str) -> None:
    part = (await admin.post(f"{V}/parts", json={"part_number": "M-1", "part_name": "Migrate"})).json()
    size = (await admin.get(f"{V}/label-types")).json()[0]["size"]["id"]
    await admin.patch(f"{V}/printers/{setup_done['printer_id']}", json={"loaded_label_size_id": size})
    await agent_alive()
    r = await admin.post(f"{V}/print", headers={"Idempotency-Key": str(uuid.uuid4())}, json={"items": [
        {"part_id": part["id"], "copies": 1, "quantity": 1, "manual_values": {}}]})
    assert r.status_code == 200, r.text
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    cfg.attributes["database_url"] = migrated
    cfg.attributes["skip_logging"] = True
    await to_thread.run_sync(command.downgrade, cfg, "0006")
    await to_thread.run_sync(command.upgrade, cfg, "head")
    await dispose_engine()  # pooled connections cached statement plans for the old table shapes
    init_engine(migrated)
    async with sessionmaker()() as db:
        assert (await db.execute(select(PrintedLabel))).scalar_one().part_id == uuid.UUID(part["id"])
    assert (await admin.get(f"{V}/parts/{part['id']}")).json()["label_state"] == "current"
