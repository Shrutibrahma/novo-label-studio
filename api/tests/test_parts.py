"""M2: parts CRUD, custom fields, images, label names; search tests (16.1) and acceptance A8."""

from __future__ import annotations

import io
from typing import Any

import httpx
import pytest
from PIL import Image
from sqlalchemy import select

from app.db import sessionmaker
from app.models import AuditLog

V = "/api/v1"


async def make_part(c: httpx.AsyncClient, number: str, name: str, **extra: Any) -> dict[str, Any]:
    r = await c.post(f"{V}/parts", json={"part_number": number, "part_name": name, **extra})
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_read_update_part(admin: httpx.AsyncClient) -> None:
    p = await make_part(admin, "  np-10421 ", "Bearing Housing", description="Cast iron", revision="C",
                        label_name="10-32 x 1/2 16")
    assert p["part_number"] == "np-10421" and p["label_name"] == "10-32 x 1/2 16"
    assert p["label_state"] == "never_printed" and p["config"]["scope"] == "default"
    assert p["config"]["size"]["name"] == "Large" and p["has_override"] is False

    r = await admin.post(f"{V}/parts", json={"part_number": "NP-10421", "part_name": "Dup"})
    assert r.status_code == 409
    assert r.json()["error"] == {"code": "PART_NUMBER_TAKEN", "message": "A part with this number already exists.",
                                 "fields": {"part_number": "A part with this number already exists."}}

    r = await admin.patch(f"{V}/parts/{p['id']}", json={"revision": "D"}, headers={"If-Match": p["updated_at"]})
    assert r.status_code == 200 and r.json()["revision"] == "D"
    r = await admin.patch(f"{V}/parts/{p['id']}", json={"revision": "E"}, headers={"If-Match": p["updated_at"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "STALE_WRITE"
    r = await admin.patch(f"{V}/parts/{p['id']}", json={"clear": ["description"]})
    assert r.json()["description"] is None

    async with sessionmaker()() as db:
        actions = (await db.execute(select(AuditLog.action).where(AuditLog.entity_id == p["id"])
                                    .order_by(AuditLog.id))).scalars().all()
        assert actions == ["part.create", "part.update", "part.update"]


async def test_part_validation_messages(admin: httpx.AsyncClient) -> None:
    r = await admin.post(f"{V}/parts", json={"part_number": " ", "part_name": "X"})
    assert r.json()["error"]["fields"] == {"part_number": "Part number is required."}
    r = await admin.post(f"{V}/parts", json={"part_number": "X" * 65, "part_name": "X"})
    assert r.json()["error"]["fields"] == {"part_number": "Part number is longer than 64 characters."}
    r = await admin.post(f"{V}/parts", json={"part_number": "A1", "part_name": "X", "revision": "R" * 17})
    assert r.json()["error"]["fields"] == {"revision": "Revision is longer than 16 characters."}


async def test_custom_fields_and_values(admin: httpx.AsyncClient) -> None:
    r = await admin.post(f"{V}/custom-fields", json={"label": "Max Torque", "data_type": "number", "required": True})
    assert r.status_code == 201 and r.json()["key"] == "max_torque"
    await admin.post(f"{V}/custom-fields", json={"label": "Finish", "data_type": "choice", "choices": ["Zinc", "Black"]})
    await admin.post(f"{V}/custom-fields", json={"label": "Released", "data_type": "date"})
    r = await admin.post(f"{V}/custom-fields", json={"label": "Other", "key": "max_torque", "data_type": "text"})
    assert r.json()["error"]["code"] == "FIELD_KEY_TAKEN"

    r = await admin.post(f"{V}/parts", json={"part_number": "C1", "part_name": "C"})
    assert r.json()["error"]["fields"] == {"custom_data.max_torque": "Max Torque is required."}
    r = await admin.post(f"{V}/parts", json={"part_number": "C1", "part_name": "C", "custom_data": {"max_torque": "lots"}})
    assert r.json()["error"]["fields"] == {"custom_data.max_torque": "Max Torque must be a number."}
    r = await admin.post(f"{V}/parts", json={"part_number": "C1", "part_name": "C",
                                             "custom_data": {"max_torque": "1,250", "finish": "zinc", "released": "3/7/2026"}})
    assert r.status_code == 201, r.text
    assert r.json()["custom_data"] == {"max_torque": 1250, "finish": "Zinc", "released": "2026-03-07"}
    pid = r.json()["id"]
    r = await admin.patch(f"{V}/parts/{pid}", json={"custom_data": {"finish": "Chrome"}})
    assert r.json()["error"]["fields"] == {"custom_data.finish": "Finish must be one of: Zinc, Black."}
    r = await admin.patch(f"{V}/parts/{pid}", json={"custom_data": {"max_torque": ""}})
    assert r.json()["error"]["code"] == "FIELD_REQUIRED"
    r = await admin.patch(f"{V}/custom-fields/max_torque", json={"data_type": "text", "label": "Torque"})
    assert r.status_code == 200 and r.json()["data_type"] == "number" and r.json()["label"] == "Torque"


async def test_archive_restore_and_status_filter(admin: httpx.AsyncClient) -> None:
    p = await make_part(admin, "AR-1", "Archivable")
    await make_part(admin, "AR-2", "Stays")
    r = await admin.post(f"{V}/parts/{p['id']}/archive")
    assert r.json()["status"] == "archived"
    active = [i["part_number"] for i in (await admin.get(f"{V}/parts")).json()["items"]]
    assert active == ["AR-2"]
    archived = [i["part_number"] for i in (await admin.get(f"{V}/parts?status=archived")).json()["items"]]
    assert archived == ["AR-1"]
    assert [i["part_number"] for i in (await admin.get(f"{V}/parts?status=archived&q=AR")).json()["items"]] == ["AR-1"]
    r = await admin.post(f"{V}/parts/{p['id']}/restore")
    assert r.json()["status"] == "active"


async def test_pagination(admin: httpx.AsyncClient) -> None:
    for i in range(7):
        await make_part(admin, f"PG-{i:02d}", f"Page part {i}")
    seen: list[str] = []
    cursor = None
    while True:
        url = f"{V}/parts?limit=3" + (f"&cursor={cursor}" if cursor else "")
        body = (await admin.get(url)).json()
        seen += [i["part_number"] for i in body["items"]]
        cursor = body["next_cursor"]
        if not cursor:
            break
    assert seen == [f"PG-{i:02d}" for i in range(7)]


def png(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


async def test_part_image_upload(admin: httpx.AsyncClient) -> None:
    p = await make_part(admin, "IMG-1", "With image")
    r = await admin.put(f"{V}/parts/{p['id']}/image", files={"file": ("photo.png", png(2400, 1200), "image/png")})
    assert r.status_code == 200 and r.json()["has_image"] is True
    img = await admin.get(f"{V}/parts/{p['id']}/image")
    assert img.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(img.content)).size == (1024, 512)
    r = await admin.put(f"{V}/parts/{p['id']}/image", files={"file": ("x.gif", b"GIF89a", "image/gif")})
    assert r.status_code == 415 and r.json()["error"]["code"] == "IMAGE_UNSUPPORTED"
    r = await admin.put(f"{V}/parts/{p['id']}/image", files={"file": ("fake.png", b"not an image", "image/png")})
    assert r.json()["error"]["code"] == "IMAGE_UNSUPPORTED"
    r = await admin.delete(f"{V}/parts/{p['id']}/image")
    assert r.json()["has_image"] is False


async def test_label_names(admin: httpx.AsyncClient) -> None:
    a = await make_part(admin, "NP-10421", "Bearing Housing")
    b = await make_part(admin, "NP-20000", "Other part")
    r = await admin.post(f"{V}/parts/{a['id']}/aliases", json={"alias": "10-32 x 1/2 16", "is_label_name": True})
    assert r.status_code == 201
    first = r.json()
    r = await admin.post(f"{V}/parts/{b['id']}/aliases", json={"alias": "10 32 X 1/2  16"})
    assert r.status_code == 409 and r.json()["error"]["message"] == "This name is already used for part NP-10421."
    r = await admin.post(f"{V}/parts/{a['id']}/aliases", json={"alias": "np-20000"})
    assert r.json()["error"] == {"code": "ALIAS_IS_PART_NUMBER", "message": "This name is another part's part number.",
                                 "fields": {"alias": "This name is another part's part number."}}
    r = await admin.post(f"{V}/parts/{a['id']}/aliases", json={"alias": " -- "})
    assert r.json()["error"]["message"] == "Enter a name with at least one letter or number."
    # A part number can't equal another part's label name.
    r = await admin.post(f"{V}/parts", json={"part_number": "10-32 X 1/2 16", "part_name": "Clash"})
    assert r.json()["error"]["message"] == "This part number is already used as a label name for part NP-10421."
    # Switching the label name.
    second = (await admin.post(f"{V}/parts/{a['id']}/aliases", json={"alias": "Housing, bearing",
                                                                     "is_label_name": True})).json()
    aliases = (await admin.get(f"{V}/parts/{a['id']}/aliases")).json()
    assert [(x["alias"], x["is_label_name"]) for x in aliases] == [("Housing, bearing", True), ("10-32 x 1/2 16", False)]
    r = await admin.patch(f"{V}/aliases/{first['id']}", json={"is_label_name": True})
    assert r.json()["is_label_name"] is True
    assert (await admin.get(f"{V}/parts/{a['id']}")).json()["label_name"] == "10-32 x 1/2 16"
    assert (await admin.delete(f"{V}/aliases/{second['id']}")).status_code == 204
    async with sessionmaker()() as db:
        actions = (await db.execute(select(AuditLog.action).where(AuditLog.entity == "part_alias")
                                    .order_by(AuditLog.id))).scalars().all()
        assert actions == ["alias.create", "alias.create", "alias.update", "alias.delete"]


@pytest.fixture
async def catalogue(admin: httpx.AsyncClient) -> dict[str, str]:
    target = await make_part(admin, "NP-10421", "Bearing Housing", description="Cast iron housing")
    await admin.post(f"{V}/parts/{target['id']}/aliases", json={"alias": "10-32 x 1/2 16", "is_label_name": True})
    decoys = [("NP-10422", "Bearing Cap"), ("NP-1049", "Shaft collar"), ("NP-20432", "10-32 nut"),
              ("SC-1032", "Socket cap screw 10-32 x 3/4"), ("NP_TEST", "Underscore part"), ("NPX-104", "Spacer")]
    for number, name in decoys:
        await make_part(admin, number, name)
    other = await make_part(admin, "HW-2", "Washer")
    await admin.post(f"{V}/parts/{other['id']}/aliases", json={"alias": "10-24 x 1/2 16", "is_label_name": True})
    return {"target": target["id"]}


@pytest.mark.parametrize("query", ["10-32", "10 32 x 1/2 16", "10-32 X 1/2 16", "NP-104", "np-10421", "bearing housing"])
async def test_search_finds_aliased_part_first(admin: httpx.AsyncClient, catalogue: dict[str, str], query: str) -> None:
    """16.1 Search + A8: every alias form in 13.4 and the part-number prefix return the aliased part first."""
    items = (await admin.get(f"{V}/parts", params={"q": query})).json()["items"]
    assert items, query
    assert items[0]["id"] == catalogue["target"], (query, [i["part_number"] for i in items])
    assert items[0]["label_name"] == "10-32 x 1/2 16"


async def test_search_underscore_is_literal(admin: httpx.AsyncClient, catalogue: dict[str, str]) -> None:
    items = (await admin.get(f"{V}/parts", params={"q": "NP_"})).json()["items"]
    assert items[0]["part_number"] == "NP_TEST"
    assert all(i["score"] < 0.9 for i in items[1:])  # "NP-..." parts are not prefix matches of "NP_"


async def test_search_searchable_custom_field(admin: httpx.AsyncClient) -> None:
    await admin.post(f"{V}/custom-fields", json={"label": "Supplier code", "data_type": "text", "searchable": True})
    await admin.post(f"{V}/custom-fields", json={"label": "Hidden code", "data_type": "text", "searchable": False})
    p = await make_part(admin, "CF-1", "Custom", custom_data={"supplier_code": "ZX-9001", "hidden_code": "QQ-77"})
    items = (await admin.get(f"{V}/parts", params={"q": "zx-900"})).json()["items"]
    assert [i["id"] for i in items] == [p["id"]]
    assert (await admin.get(f"{V}/parts", params={"q": "QQ-77"})).json()["items"] == []


async def test_operator_parts_are_read_only(admin: httpx.AsyncClient, operator: httpx.AsyncClient) -> None:
    p = await make_part(admin, "RO-1", "Read only")
    alias = (await admin.post(f"{V}/parts/{p['id']}/aliases", json={"alias": "ro name"})).json()
    assert (await operator.get(f"{V}/parts")).status_code == 200
    assert (await operator.get(f"{V}/parts/{p['id']}")).status_code == 200
    assert (await operator.get(f"{V}/custom-fields")).status_code == 200
    checks = [
        ("POST", "/parts", {"part_number": "X", "part_name": "X"}),
        ("PATCH", f"/parts/{p['id']}", {"part_name": "Y"}),
        ("POST", f"/parts/{p['id']}/archive", None),
        ("POST", f"/parts/{p['id']}/restore", None),
        ("DELETE", f"/parts/{p['id']}/image", None),
        ("POST", f"/parts/{p['id']}/aliases", {"alias": "zzz"}),
        ("PATCH", f"/aliases/{alias['id']}", {"alias": "yyy"}),
        ("DELETE", f"/aliases/{alias['id']}", None),
        ("POST", "/custom-fields", {"label": "F", "data_type": "text"}),
        ("PATCH", "/custom-fields/anything", {"label": "F"}),
    ]
    for method, path, body in checks:
        r = await operator.request(method, f"{V}{path}", json=body)
        assert r.status_code == 403, (method, path)
    r = await operator.put(f"{V}/parts/{p['id']}/image", files={"file": ("a.png", png(10, 10), "image/png")})
    assert r.status_code == 403
