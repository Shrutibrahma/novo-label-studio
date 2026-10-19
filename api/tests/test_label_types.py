"""Saved label types (migration 0003): each type has its own versioned default and per-part overrides;
preview and print pick a type; history names it."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from sqlalchemy import select

from app.db import sessionmaker
from app.models import PrintedLabel
from tests.helpers import agent_alive

V = "/api/v1"


async def sizes(c: httpx.AsyncClient) -> dict[str, str]:
    return {s["name"]: s["id"] for s in (await c.get(f"{V}/sizes")).json()}


async def test_label_types_lifecycle_and_printing(admin: httpx.AsyncClient, operator: httpx.AsyncClient,
                                                  setup_done: dict[str, Any]) -> None:
    types = (await admin.get(f"{V}/label-types")).json()
    assert [t["name"] for t in types] == ["Label"] and types[0]["layout"] == "lines"
    label_id = types[0]["id"]

    # A new type starts as a copy of the first type's design, as version 1 of its own default.
    r = await admin.post(f"{V}/label-types", json={"name": "Bin"})
    assert r.status_code == 201, r.text
    bin_type = r.json()
    assert bin_type["version"] == 1 and bin_type["size"] == types[0]["size"]
    r = await admin.post(f"{V}/label-types", json={"name": " bin "})
    assert r.status_code == 409 and r.json()["error"]["code"] == "LABEL_TYPE_EXISTS"
    assert (await operator.post(f"{V}/label-types", json={"name": "Rack"})).status_code == 403
    assert [t["name"] for t in (await operator.get(f"{V}/label-types")).json()] == ["Label", "Bin"]

    # Publishing the Bin default doesn't touch the Label default.
    size_ids = await sizes(admin)
    grid = {"rows": [{"cells": [{"kind": "field", "key": "part_number", "heading": "BIN"}]}]}
    spec = {"fields": [], "manual_fields": [], "style": {"layout": "grid"}, "grid": grid}
    r = await admin.post(f"{V}/configs", json={"scope": "default", "label_type_id": bin_type["id"], "spec": spec,
                                               "label_size_id": size_ids["Small"], "qr_mode": "none",
                                               "serial_mode": "none"})
    assert r.status_code == 201, r.text
    assert r.json()["label_type_name"] == "Bin" and r.json()["version"] == 2
    label_default = (await admin.get(f"{V}/configs/default")).json()
    assert label_default["label_type_name"] == "Label" and label_default["version"] == 1
    assert (await admin.get(f"{V}/configs/default", params={"type_id": bin_type["id"]})).json()["version"] == 2

    # Per-part override for one type only.
    part = (await admin.post(f"{V}/parts", json={"part_number": "T-1", "part_name": "Typed part"})).json()
    r = await admin.post(f"{V}/configs", json={"scope": "part", "part_id": part["id"], "label_type_id": bin_type["id"],
                                               "spec": spec, "label_size_id": size_ids["Large"], "qr_mode": "none",
                                               "serial_mode": "none"})
    assert r.status_code == 201, r.text
    assert (await admin.get(f"{V}/parts/{part['id']}/config")).json()["scope"] == "default"
    bin_cfg = (await admin.get(f"{V}/parts/{part['id']}/config", params={"type_id": bin_type["id"]})).json()
    assert bin_cfg["scope"] == "part" and bin_cfg["size"]["name"] == "Large"
    listed = (await admin.get(f"{V}/configs", params={"type_id": bin_type["id"]})).json()
    assert [o["part_number"] for o in listed["overrides"]] == ["T-1"]
    assert (await admin.get(f"{V}/configs")).json()["overrides"] == []

    # Preview and print use the chosen type; history names it.
    preview = (await admin.post(f"{V}/render/preview", json={"part_id": part["id"], "label_type_id": bin_type["id"]})).json()
    assert preview["family"] == "grid"
    assert (await admin.post(f"{V}/render/preview", json={"part_id": part["id"]})).json()["family"] != "grid"
    await admin.patch(f"{V}/printers/{setup_done['printer_id']}", json={"loaded_label_size_id": size_ids["Large"]})
    await agent_alive()
    r = await admin.post(f"{V}/print", headers={"Idempotency-Key": str(uuid.uuid4())},
                         json={"label_type_id": bin_type["id"],
                               "items": [{"part_id": part["id"], "copies": 1, "quantity": 1, "manual_values": {}}]})
    assert r.status_code == 200, r.text
    async with sessionmaker()() as db:
        pl = (await db.execute(select(PrintedLabel))).scalar_one()
    assert pl.label_config_id == uuid.UUID(bin_cfg["id"])
    assert (await admin.get(f"{V}/labels/{pl.id}")).json()["label_type"] == "Bin"

    # Rename, reorder, archive (never the last one); archived types disappear but their history stays.
    r = await admin.patch(f"{V}/label-types/{bin_type['id']}", json={"name": "Bin card", "sort_order": 0})
    assert r.json()["name"] == "Bin card"
    assert (await admin.post(f"{V}/label-types/{bin_type['id']}/archive")).status_code == 204
    assert [t["name"] for t in (await admin.get(f"{V}/label-types")).json()] == ["Label"]
    assert (await admin.get(f"{V}/labels/{pl.id}")).json()["label_type"] == "Bin card"
    r = await admin.post(f"{V}/label-types/{label_id}/archive")
    assert r.status_code == 422 and r.json()["error"]["message"] == "Keep at least one label type."
    r = await admin.post(f"{V}/label-types", json={"name": "Bin"})  # the name is free again
    assert r.status_code == 201
