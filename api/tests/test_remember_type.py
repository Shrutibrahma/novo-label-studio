"""Each part remembers its label type (v1.1 U2, D11 amended): resolution order preferred → last printed →
"Print as" → first, used by part reads, preview and print."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from sqlalchemy import select

from app.db import sessionmaker
from app.models import LabelConfig, PrintedLabel
from tests.helpers import agent_alive

V = "/api/v1"


async def new_type(admin: httpx.AsyncClient, name: str) -> dict[str, Any]:
    r = await admin.post(f"{V}/label-types", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


async def print_part(c: httpx.AsyncClient, part_id: str, **item: Any) -> httpx.Response:
    return await c.post(f"{V}/print", headers={"Idempotency-Key": str(uuid.uuid4())},
                        json={"items": [{"part_id": part_id, "copies": 1, "quantity": 1, "manual_values": {}} | item]})


async def resolved(c: httpx.AsyncClient, part_id: str, print_as: str | None = None) -> tuple[str, str]:
    params = {"print_as": print_as} if print_as else {}
    t = (await c.get(f"{V}/parts/{part_id}", params=params)).json()["label_type"]
    return t["name"], t["reason"]


async def test_resolution_order(admin: httpx.AsyncClient, operator: httpx.AsyncClient,
                                setup_done: dict[str, Any]) -> None:
    label = (await admin.get(f"{V}/label-types")).json()[0]
    bin_type, rack = await new_type(admin, "Bin"), await new_type(admin, "Rack")
    part = (await admin.post(f"{V}/parts", json={"part_number": "NP-10421", "part_name": "Bearing"})).json()

    assert await resolved(operator, part["id"]) == ("Label", "first")
    assert await resolved(operator, part["id"], rack["id"]) == ("Rack", "print_as")
    items = (await operator.get(f"{V}/parts", params={"print_as": rack["id"]})).json()["items"]
    assert [(i["label_type"]["name"], i["label_type"]["reason"]) for i in items] == [("Rack", "print_as")]
    assert len(items) == 1  # one row per part, whatever the number of types

    # Printing records the type: it becomes last_printed. Reprints don't count.
    await admin.patch(f"{V}/printers/{setup_done['printer_id']}",
                      json={"loaded_label_size_id": bin_type["size"]["id"]})
    await agent_alive()
    r = await print_part(operator, part["id"], label_type_id=bin_type["id"])
    assert r.status_code == 200, r.text
    assert await resolved(operator, part["id"], rack["id"]) == ("Bin", "last_printed")
    async with sessionmaker()() as db:
        first_label = (await db.execute(select(PrintedLabel))).scalar_one()
    r = await print_part(operator, part["id"])  # no type given: the resolved one (Bin)
    async with sessionmaker()() as db:
        cfg_types = {(await db.get(LabelConfig, pl.label_config_id)).label_type_id  # type: ignore[union-attr]
                     for pl in (await db.execute(select(PrintedLabel))).scalars()}
    assert cfg_types == {uuid.UUID(bin_type["id"])}
    r = await operator.post(f"{V}/labels/{first_label.id}/reprint", headers={"Idempotency-Key": str(uuid.uuid4())},
                            json={"reason": "damaged"})
    assert r.status_code == 200, r.text

    # Preferred wins over last printed; operators can't set it; archived preferred types are skipped.
    assert (await operator.patch(f"{V}/parts/{part['id']}", json={"preferred_label_type_id": rack["id"]})
            ).status_code == 403
    r = await admin.patch(f"{V}/parts/{part['id']}", json={"preferred_label_type_id": rack["id"]})
    assert r.status_code == 200 and r.json()["preferred_label_type_id"] == rack["id"]
    assert await resolved(operator, part["id"]) == ("Rack", "preferred")
    assert (await admin.post(f"{V}/label-types/{rack['id']}/archive")).status_code == 204
    assert await resolved(operator, part["id"]) == ("Bin", "last_printed")
    assert (await admin.patch(f"{V}/parts/{part['id']}", json={"preferred_label_type_id": None})).status_code == 200
    assert (await admin.patch(f"{V}/parts/{part['id']}", json={"preferred_label_type_id": rack["id"]})
            ).status_code == 404  # archived
    # Preview without a type uses the same order.
    preview = (await operator.post(f"{V}/render/preview", json={"part_id": part["id"]})).json()
    preview_bin = (await operator.post(f"{V}/render/preview", json={"part_id": part["id"],
                                                                    "label_type_id": bin_type["id"]})).json()
    assert preview["png_base64"] == preview_bin["png_base64"]
    assert label["name"] == "Label"


async def test_print_saves_or_clears_the_preferred_type(admin: httpx.AsyncClient, operator: httpx.AsyncClient,
                                                        setup_done: dict[str, Any]) -> None:
    bin_type = await new_type(admin, "Bin")
    part = (await admin.post(f"{V}/parts", json={"part_number": "P-2", "part_name": "Washer"})).json()
    await admin.patch(f"{V}/printers/{setup_done['printer_id']}",
                      json={"loaded_label_size_id": bin_type["size"]["id"]})
    await agent_alive()
    assert (await print_part(operator, part["id"], label_type_id=bin_type["id"], set_preferred=True)
            ).status_code == 403
    assert (await print_part(admin, part["id"], label_type_id=bin_type["id"], set_preferred=True)).status_code == 200
    detail = (await admin.get(f"{V}/parts/{part['id']}")).json()
    assert detail["preferred_label_type_id"] == bin_type["id"] and detail["label_type"]["reason"] == "preferred"
    assert detail["config"]["label_type_id"] == bin_type["id"]
    assert (await print_part(admin, part["id"], label_type_id=bin_type["id"], set_preferred=False)).status_code == 200
    detail = (await admin.get(f"{V}/parts/{part['id']}")).json()
    assert detail["preferred_label_type_id"] is None and detail["label_type"]["reason"] == "last_printed"


async def test_batch_mixes_types(admin: httpx.AsyncClient, setup_done: dict[str, Any]) -> None:
    bin_type = await new_type(admin, "Bin")
    a = (await admin.post(f"{V}/parts", json={"part_number": "A-1", "part_name": "Alpha"})).json()
    b = (await admin.post(f"{V}/parts", json={"part_number": "B-1", "part_name": "Beta"})).json()
    await admin.patch(f"{V}/parts/{b['id']}", json={"preferred_label_type_id": bin_type["id"]})
    await admin.patch(f"{V}/printers/{setup_done['printer_id']}",
                      json={"loaded_label_size_id": bin_type["size"]["id"]})
    await agent_alive()
    r = await admin.post(f"{V}/print", headers={"Idempotency-Key": str(uuid.uuid4())}, json={"items": [
        {"part_id": a["id"], "copies": 1, "quantity": 1, "manual_values": {}},
        {"part_id": b["id"], "copies": 1, "quantity": 1, "manual_values": {}}]})
    assert r.status_code == 200, r.text
    async with sessionmaker()() as db:
        rows = (await db.execute(select(PrintedLabel).order_by(PrintedLabel.seq_in_job))).scalars().all()
        types = [(await db.get(LabelConfig, pl.label_config_id)).label_type_id for pl in rows]  # type: ignore[union-attr]
        houses = [pl.snapshot["generated"]["house_style"]["title"] for pl in rows]
    first = (await admin.get(f"{V}/label-types")).json()[0]
    assert types == [uuid.UUID(first["id"]), uuid.UUID(bin_type["id"])]
    assert houses == ["Label", "Bin"]


async def test_import_label_type_column(admin: httpx.AsyncClient) -> None:
    from tests.test_imports import csv_bytes, map_and_stage, rows, upload

    bin_type = await new_type(admin, "Bin")
    table = [["Part Number", "Part Name", "Label type"],
             ["IM-1", "First", " bin "], ["IM-2", "Second", "Nope"], ["IM-3", "Third", ""]]
    batch = await upload(admin, "types.csv", csv_bytes(table))
    assert batch["mapping"]["Label type"] == "label_type"
    await map_and_stage(admin, batch)
    staged = {r["data"]["part_number"]: r for r in await rows(admin, batch["id"])}
    assert staged["IM-1"]["action"] == "new" and staged["IM-1"]["data"]["label_type"] == "Bin"
    assert staged["IM-2"]["action"] == "new" and staged["IM-2"]["accepted"]
    assert staged["IM-2"]["errors"] == [{"field": "label_type", "level": "warning",
                                         "msg": 'Unknown label type "Nope"; the part keeps its current type.'}]
    assert (await admin.post(f"{V}/imports/{batch['id']}/commit")).status_code == 200
    parts = {p["part_number"]: p for p in (await admin.get(f"{V}/parts")).json()["items"]}
    assert parts["IM-1"]["label_type"] == {"id": bin_type["id"], "name": "Bin", "reason": "preferred"}
    assert parts["IM-2"]["label_type"]["reason"] == "first"

    # Re-import: an empty cell keeps the preferred type; another name changes it (shown in the diff).
    rack = await new_type(admin, "Rack")
    batch = await upload(admin, "types2.csv", csv_bytes([["Part Number", "Part Name", "Label type"],
                                                         ["IM-1", "First", ""], ["IM-3", "Third", "Rack"]]))
    await map_and_stage(admin, batch)
    staged = {r["data"]["part_number"]: r for r in await rows(admin, batch["id"]) if r["action"] != "missing"}
    assert staged["IM-1"]["action"] == "unchanged"
    assert staged["IM-3"]["diff"] == {"label_type": [None, "Rack"]}
    assert (await admin.post(f"{V}/imports/{batch['id']}/commit")).status_code == 200
    parts = {p["part_number"]: p for p in (await admin.get(f"{V}/parts")).json()["items"]}
    assert parts["IM-1"]["label_type"]["name"] == "Bin" and parts["IM-3"]["label_type"]["id"] == rack["id"]
