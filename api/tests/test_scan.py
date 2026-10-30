"""The part page a QR code opens (owner's request, 2026-10-30): GET /scan/{part number}, /scan/serial/{serial}."""

from __future__ import annotations

from typing import Any

import httpx

from app.render.snapshot import qr_payload

V = "/api/v1"


def test_link_payloads_are_capitals_for_a_small_qr_code() -> None:
    base = "https://192.168.1.20:8443/"
    assert qr_payload("part", "np-10421", None, None, base) == "HTTPS://192.168.1.20:8443/P/NP-10421"
    assert qr_payload("serial", "NP-1", "NOVO-00000007", None, base) == "HTTPS://192.168.1.20:8443/S/NOVO-00000007"
    assert qr_payload("part", "A/B 1", None, None, base) == "HTTPS://192.168.1.20:8443/P/A%2FB%201"
    assert qr_payload("part", "NP-1", None, None, None) == "PN:NP-1"  # links off
    assert qr_payload("part", "NP-1", None, [("Name", "x")], base) == "PN:NP-1\nName: x"  # label data stays text
    assert qr_payload("none", "NP-1", None, None, base) is None


async def test_scan_page_needs_sign_in_unless_public(admin: httpx.AsyncClient, new_client: Any) -> None:
    await admin.post(f"{V}/parts", json={"part_number": "A/B 1", "part_name": "Slash part", "description": "Thin",
                                         "revision": "C"})
    r = await admin.get(f"{V}/scan/a%2Fb%201")
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["part_number"], body["part_name"], body["revision"]) == ("A/B 1", "Slash part", "C")
    assert body["part_id"] and body["serial"] is None and body["image_url"] is None
    assert (await admin.get(f"{V}/scan/NOPE")).status_code == 404
    assert (await admin.get(f"{V}/scan/serial/NOVO-00000099")).status_code == 404

    anon = new_client()  # no session cookie
    assert (await anon.get(f"{V}/scan/A%2FB%201")).status_code == 401
    r = await admin.patch(f"{V}/settings", json={"scan_public": True})
    assert r.status_code == 200 and r.json()["qr"]["scan_public"] is True
    r = await anon.get(f"{V}/scan/A%2FB%201")
    assert r.status_code == 200 and r.json()["part_id"] is None  # no "Open in the app" for anonymous viewers


async def test_qr_link_settings(admin: httpx.AsyncClient) -> None:
    qr = (await admin.get(f"{V}/settings")).json()["qr"]
    assert qr == {"link": False, "link_base": "https://localhost:8443", "scan_public": False}
    r = await admin.patch(f"{V}/settings", json={"qr_link_base": "  https://192.168.1.20:8443/ "})
    assert r.json()["qr"]["link_base"] == "https://192.168.1.20:8443"
    r = await admin.patch(f"{V}/settings", json={"qr_link_base": "192.168.1.20"})
    assert r.status_code == 422 and "qr_link_base" in r.json()["error"]["fields"]
