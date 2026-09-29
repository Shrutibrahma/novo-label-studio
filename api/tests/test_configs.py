"""M4: label configs (versions, overrides, selection) and POST /render/preview."""

from __future__ import annotations

import base64
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import func, select, text

from app.configs.spec import LabelSpec
from app.db import sessionmaker
from app.models import AuditLog, IssuedSerial, LabelConfig
from app.render.engine import RenderConfig, RenderPrinter, RenderSize, render
from app.render.fonts import renderer_version

V = "/api/v1"

STYLE = {"font": "inter", "primary_weight": "bold", "alignment": "left", "emphasis": "medium",
         "spacing": "standard", "qr_position": "right"}


def fields(*keys: str) -> list[dict[str, Any]]:
    roles = ["primary", "secondary", "secondary", "detail", "detail", "detail", "detail", "detail", "detail"]
    return [{"key": k, "role": roles[i], "uppercase": False, "caption": None} for i, k in enumerate(keys)]


async def sizes(c: httpx.AsyncClient) -> dict[str, str]:
    return {s["name"]: s["id"] for s in (await c.get(f"{V}/sizes")).json()}


async def part(c: httpx.AsyncClient, number: str = "NP-10421", name: str = "Bearing Housing") -> dict[str, Any]:
    r = await c.post(f"{V}/parts", json={"part_number": number, "part_name": name, "revision": "C",
                                         "label_name": "10-32 x 1/2 16"})
    assert r.status_code == 201, r.text
    return r.json()


async def test_publish_default_versions(admin: httpx.AsyncClient) -> None:
    current = (await admin.get(f"{V}/configs/default")).json()
    assert current["version"] == 1
    body = {"scope": "default", "label_size_id": (await sizes(admin))["Medium"],
            "spec": {"fields": fields("label_name", "part_number"), "manual_fields": [], "style": STYLE},
            "qr_mode": "part", "serial_mode": "none", "base_config_id": current["id"]}
    r = await admin.post(f"{V}/configs", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["version"] == 2 and r.json()["config_key"] == current["config_key"]
    assert (await admin.post(f"{V}/configs", json=body)).json()["error"]["code"] == "STALE_WRITE"
    async with sessionmaker()() as db:
        rows = (await db.execute(select(LabelConfig.version, LabelConfig.is_current).order_by(LabelConfig.version))).all()
        assert rows == [(1, False), (2, True)]
        assert (await db.execute(select(func.count()).select_from(AuditLog)
                                 .where(AuditLog.action == "config.publish"))).scalar() == 2  # setup + this


async def test_config_validation(admin: httpx.AsyncClient) -> None:
    size = (await sizes(admin))["Large"]
    base = {"scope": "default", "label_size_id": size, "qr_mode": "none", "serial_mode": "none"}
    too_many = [{"key": k, "role": "secondary", "uppercase": False, "caption": None}
                for k in ("part_number", "part_name", "revision")]
    r = await admin.post(f"{V}/configs", json=base | {"spec": {"fields": too_many, "manual_fields": [], "style": STYLE}})
    assert r.json()["error"] == {"code": "CONFIG_ROLE_LIMIT",
                                 "message": "A label can have 1 main line, 2 second lines and 6 detail lines."}
    r = await admin.post(f"{V}/configs", json=base | {"qr_mode": "serial",
                                                      "spec": {"fields": fields("part_number"), "manual_fields": [], "style": STYLE}})
    assert r.json()["error"]["message"] == "Turn on serial numbers to use a serial QR code."
    r = await admin.post(f"{V}/configs", json=base | {"spec": {"fields": fields("nope"), "manual_fields": [], "style": STYLE}})
    assert r.json()["error"]["code"] == "CONFIG_FIELD_UNKNOWN"
    r = await admin.post(f"{V}/configs", json=base | {"spec": {"fields": fields("part_number"), "style": STYLE,
                                                               "manual_fields": [{"key": "box", "label": "Box", "type": "box_sequence", "noun": "box"}]}})
    assert r.json()["error"]["code"] == "CONFIG_INVALID"


async def test_part_override_lifecycle(admin: httpx.AsyncClient) -> None:
    p = await part(admin)
    size = (await sizes(admin))["Tall"]
    spec = {"fields": fields("label_name", "part_number", "serial") + [
        {"key": "manual.box", "role": "detail", "uppercase": True, "caption": None}],
        "manual_fields": [{"key": "box", "label": "Box", "type": "box_sequence", "noun": "BOX", "required": True}],
        "style": STYLE}
    r = await admin.post(f"{V}/configs", json={"scope": "part", "part_id": p["id"], "label_size_id": size, "spec": spec,
                                               "qr_mode": "serial", "serial_mode": "required"})
    assert r.status_code == 201 and r.json()["version"] == 1, r.text  # 13.9: "publishes v1 for this part"
    eff = (await admin.get(f"{V}/parts/{p['id']}/config")).json()
    assert eff["scope"] == "part" and eff["size"]["name"] == "Tall"
    detail = (await admin.get(f"{V}/parts/{p['id']}")).json()
    assert detail["has_override"] is True and detail["config"]["version"] == 1
    listing = (await admin.get(f"{V}/configs")).json()
    assert [o["part_number"] for o in listing["overrides"]] == ["NP-10421"]
    assert listing["overrides"][0]["label_name"] == "10-32 x 1/2 16"

    r = await admin.delete(f"{V}/parts/{p['id']}/config")
    assert r.json()["scope"] == "default"
    assert (await admin.get(f"{V}/parts/{p['id']}")).json()["has_override"] is False
    assert (await admin.get(f"{V}/configs")).json()["overrides"] == []
    assert (await admin.get(f"{V}/parts/{p['id']}/config")).json()["next_version"] == 2
    r = await admin.post(f"{V}/configs", json={"scope": "part", "part_id": p["id"], "label_size_id": size, "spec": spec,
                                               "qr_mode": "none", "serial_mode": "none"})
    assert r.json()["version"] == 2  # same config_key keeps counting


async def test_selection_by_operator(admin: httpx.AsyncClient, operator: httpx.AsyncClient) -> None:
    p = await part(admin)
    sz = await sizes(admin)
    body = {"fields": fields("label_name", "part_number", "revision"), "label_size_id": sz["Medium"], "emphasis": "large"}
    r = await operator.put(f"{V}/parts/{p['id']}/selection", json=body)
    assert r.status_code == 200, r.text
    cfg = r.json()
    assert (cfg["scope"], cfg["version"], cfg["size"]["name"]) == ("part", 1, "Medium")
    assert cfg["spec"]["style"]["emphasis"] == "large" and cfg["spec"]["style"]["font"] == "inter"
    assert [f["key"] for f in cfg["spec"]["fields"]] == ["label_name", "part_number", "revision"]
    # Same selection again: no new version.
    again = (await operator.put(f"{V}/parts/{p['id']}/selection", json=body)).json()
    assert again["id"] == cfg["id"]
    # Selection can't smuggle in unknown fields.
    bad = body | {"fields": fields("label_name", "manual.nothing")}
    assert (await operator.put(f"{V}/parts/{p['id']}/selection", json=bad)).json()["error"]["code"] == "CONFIG_FIELD_UNKNOWN"
    # Everything else still needs an admin.
    publish = {"scope": "part", "part_id": p["id"], "label_size_id": sz["Large"], "qr_mode": "none", "serial_mode": "none",
               "spec": {"fields": fields("part_number"), "manual_fields": [], "style": STYLE}}
    assert (await operator.post(f"{V}/configs", json=publish)).status_code == 403
    assert (await operator.delete(f"{V}/parts/{p['id']}/config")).status_code == 403
    assert (await operator.get(f"{V}/configs")).status_code == 403
    assert (await operator.get(f"{V}/configs/default")).status_code == 200


async def test_preview_matches_renderer_and_never_allocates(admin: httpx.AsyncClient) -> None:
    await admin.patch(f"{V}/settings", json={"serial_digits": 6})
    p = await part(admin)
    size = (await sizes(admin))["Large"]
    spec = {"fields": fields("label_name", "part_number", "serial", "print_date"), "manual_fields": [], "style": STYLE}
    draft = {"label_size_id": size, "spec": spec, "qr_mode": "serial", "serial_mode": "required"}
    r = await admin.post(f"{V}/render/preview", json={"part_id": p["id"], "config": draft},
                         headers={"X-Timezone": "Pacific/Kiritimati"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fits"] and body["serial_placeholder"] and (body["width_dots"], body["height_dots"], body["dpi"]) == (812, 406, 203)
    # Rebuild the exact expected image: serial = prefix + separator + one 8 per digit; print_date in that zone.
    async with sessionmaker()() as db:
        today = (await db.execute(text("SELECT (now() AT TIME ZONE 'Pacific/Kiritimati')::date"))).scalar()
        assert (await db.execute(select(func.count()).select_from(IssuedSerial))).scalar() == 0
    snapshot = {"part": {"label_name": "10-32 x 1/2 16", "part_number": "NP-10421"}, "manual": {},
                "generated": {"print_date": today.isoformat(), "renderer_version": renderer_version(),
                              "serial": "NOVO-888888", "qr_payload": "SN:NOVO-888888|PN:NP-10421"}}
    expected = render(snapshot, RenderConfig(LabelSpec.model_validate(spec), "serial", {}),
                      RenderSize(Decimal("4.000"), Decimal("2.000")), RenderPrinter(203, Decimal("4.100")))
    assert base64.b64decode(body["png_base64"]) == expected.png


async def test_preview_warnings_and_manual_values(admin: httpx.AsyncClient, operator: httpx.AsyncClient) -> None:
    p = await part(admin)
    size = (await sizes(admin))["Small"]
    spec = {"fields": fields("part_number") + [{"key": "manual.lot", "role": "detail", "uppercase": False, "caption": "LOT"}],
            "manual_fields": [{"key": "lot", "label": "Lot", "type": "number", "min": 1, "max": 99, "integer": True,
                               "required": True}], "style": STYLE}
    draft = {"label_size_id": size, "spec": spec, "qr_mode": "none", "serial_mode": "none"}
    body = (await operator.post(f"{V}/render/preview", json={"part_id": p["id"], "config": draft})).json()
    assert body["fits"] is False and body["warnings"] == [
        {"code": "REQUIRED_VALUE_MISSING", "field": "manual.lot", "message": "Enter Lot to print."}]
    ok = (await operator.post(f"{V}/render/preview", json={"part_id": p["id"], "config": draft,
                                                           "manual_values": {"lot": "42"}})).json()
    assert ok["fits"] is True
    r = await operator.post(f"{V}/render/preview", json={"part_id": p["id"], "config": draft, "manual_values": {"lot": 120}})
    assert r.status_code == 422 and r.json()["error"]["fields"] == {"manual_values.lot": "Lot must be between 1 and 99."}
    # The stored effective config works without a draft.
    assert (await operator.post(f"{V}/render/preview", json={"part_id": p["id"]})).json()["fits"] is True
