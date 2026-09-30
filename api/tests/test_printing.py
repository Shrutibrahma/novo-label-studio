"""M5: serials, print requests/jobs, agent endpoints, box sets, copies vs quantity (sections 8, 9; 16.1)."""

from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select, text

from app.db import sessionmaker
from app.models import IssuedSerial, LabelGroup, PrintedLabel, PrintJob, SerialSequence
from app.printing.agent_router import expire_leases
from tests.helpers import agent_alive

V = "/api/v1"
STYLE = {"font": "inter", "primary_weight": "bold", "alignment": "left", "emphasis": "medium",
         "spacing": "standard", "qr_position": "right"}


def key() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid.uuid4())}


def fields(*keys: str) -> list[dict[str, Any]]:
    roles = ["primary", "secondary", "detail", "detail", "detail", "detail"]
    return [{"key": k, "role": roles[i], "uppercase": False, "caption": None} for i, k in enumerate(keys)]


async def size_ids(c: httpx.AsyncClient) -> dict[str, str]:
    return {s["name"]: s["id"] for s in (await c.get(f"{V}/sizes")).json()}


@pytest.fixture
async def ready(admin: httpx.AsyncClient, setup_done: dict[str, Any]) -> dict[str, Any]:
    """A part with a serialized override on Large labels, the printer loaded with Large, and a live agent."""
    sizes = await size_ids(admin)
    part = (await admin.post(f"{V}/parts", json={"part_number": "NP-10421", "part_name": "Bearing Housing",
                                                 "label_name": "10-32 x 1/2 16", "revision": "C"})).json()
    spec = {"fields": fields("label_name", "part_number", "serial") +
            [{"key": "manual.box", "role": "detail", "uppercase": True, "caption": None}],
            "manual_fields": [{"key": "box", "label": "Box", "type": "box_sequence", "noun": "BOX", "required": True}],
            "style": STYLE}
    r = await admin.post(f"{V}/configs", json={"scope": "part", "part_id": part["id"], "label_size_id": sizes["Large"],
                                               "spec": spec, "qr_mode": "serial", "serial_mode": "required"})
    assert r.status_code == 201, r.text
    plain = (await admin.post(f"{V}/parts", json={"part_number": "NP-2", "part_name": "Plain washer"})).json()
    await admin.patch(f"{V}/printers/{setup_done['printer_id']}", json={"loaded_label_size_id": sizes["Large"]})
    await agent_alive()
    return {"part": part, "plain": plain, "sizes": sizes, "printer_id": setup_done["printer_id"],
            "token": setup_done["agent_token"]}


def agent_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_print_one_label_and_idempotency(admin: httpx.AsyncClient, ready: dict[str, Any]) -> None:
    body = {"items": [{"part_id": ready["part"]["id"], "copies": 2, "quantity": 1, "manual_values": {}}]}
    r = await admin.post(f"{V}/print", json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    headers = key()
    r = await admin.post(f"{V}/print", json=body, headers=headers)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["serials"] == ["NOVO-00000001"] and len(out["jobs"]) == 1
    job = out["jobs"][0]
    assert job["status"] == "queued" and job["labels"][0]["copies"] == 2
    again = (await admin.post(f"{V}/print", json=body, headers=headers)).json()
    assert again["request_id"] == out["request_id"] and again["jobs"][0]["id"] == job["id"]
    async with sessionmaker()() as db:
        pl = (await db.execute(select(PrintedLabel))).scalar_one()
        assert pl.snapshot["part"] == {"label_name": "10-32 x 1/2 16", "part_number": "NP-10421"}
        assert pl.snapshot["manual"] == {"box": {"index": 1, "total": 1}}
        assert pl.snapshot["generated"]["serial"] == "NOVO-00000001"
        assert pl.qr_payload == "SN:NOVO-00000001|PN:NP-10421" and pl.dpi == 203
        zpl = (await db.get(PrintJob, pl.job_id)).payload_zpl.decode()  # type: ignore[union-attr]
        assert zpl.count("^XA") == 1 and "^PQ2\n" in zpl and "^PW812\n^LL406\n" in zpl
        serial = await db.get(IssuedSerial, "NOVO-00000001")
        assert serial is not None and serial.status == "allocated"


async def test_print_blocking(admin: httpx.AsyncClient, ready: dict[str, Any]) -> None:
    body = {"items": [{"part_id": ready["plain"]["id"]}]}
    for status, message in [("out_of_media", "The printer is out of labels."), ("head_open", "The printer cover is open."),
                            ("offline", "The printer is offline. Check the USB cable and that the printer is on."),
                            ("paused", "The printer is paused. Press the pause button on the printer.")]:
        await agent_alive(status)
        r = await admin.post(f"{V}/print", json=body, headers=key())
        assert r.status_code == 409 and r.json()["error"]["message"] == message
    await agent_alive("ready")
    async with sessionmaker()() as db:
        await db.execute(text("UPDATE print_agent SET last_seen_at = now() - interval '31 seconds'"))
        await db.commit()
    r = await admin.post(f"{V}/print", json=body, headers=key())
    assert r.json()["error"]["message"] == "The print agent on the laptop isn't responding."


async def test_loaded_size_must_match_until_confirmed(admin: httpx.AsyncClient, ready: dict[str, Any]) -> None:
    await admin.patch(f"{V}/printers/{ready['printer_id']}", json={"loaded_label_size_id": ready["sizes"]["Small"]})
    body = {"items": [{"part_id": ready["plain"]["id"]}]}
    r = await admin.post(f"{V}/print", json=body, headers=key())
    assert r.status_code == 409 and r.json()["error"]["message"] == "Load Large labels in the printer, then confirm."
    r = await admin.post(f"{V}/print", json=body | {"loaded_size_confirmed": True}, headers=key())
    assert r.status_code == 200
    printer = (await admin.get(f"{V}/printers/{ready['printer_id']}")).json()
    assert printer["loaded_label_size"]["name"] == "Large"


async def test_quantity_vs_copies(admin: httpx.AsyncClient, ready: dict[str, Any]) -> None:
    r = await admin.post(f"{V}/print", json={"items": [{"part_id": ready["part"]["id"], "quantity": 3, "copies": 4}]},
                         headers=key())
    out = r.json()
    assert out["serials"] == ["NOVO-00000001", "NOVO-00000002", "NOVO-00000003"]
    assert [lbl["copies"] for lbl in out["jobs"][0]["labels"]] == [4, 4, 4]
    r = await admin.post(f"{V}/print", json={"items": [{"part_id": ready["plain"]["id"], "quantity": 2}]}, headers=key())
    assert r.status_code == 422 and r.json()["error"]["fields"] == {"quantity": "Quantity must be between 1 and 1."}
    r = await admin.post(f"{V}/print", json={"items": [{"part_id": ready["plain"]["id"], "copies": 51}]}, headers=key())
    assert r.json()["error"]["code"] == "FIELD_OUT_OF_RANGE"


async def test_box_set(admin: httpx.AsyncClient, ready: dict[str, Any]) -> None:
    """A5 logic: "Print all 3 boxes" gives BOX 1/3, 2/3, 3/3 with 3 distinct serials; single boxes reuse the group."""
    part = ready["part"]["id"]
    out = (await admin.post(f"{V}/print", json={"items": [{"part_id": part, "group": {"total": 3, "start_index": 1}}]},
                            headers=key())).json()
    labels = out["jobs"][0]["labels"]
    assert [lbl["group_index"] for lbl in labels] == [1, 2, 3] and len(set(out["serials"])) == 3
    async with sessionmaker()() as db:
        snaps = [pl.snapshot["manual"]["box"] for pl in (await db.execute(select(PrintedLabel).order_by(PrintedLabel.seq_in_job))).scalars()]
        assert snaps == [{"index": 1, "total": 3}, {"index": 2, "total": 3}, {"index": 3, "total": 3}]
    one = (await admin.post(f"{V}/print", json={"items": [{"part_id": part, "group": {"total": 3, "start_index": 1, "count": 1}}]},
                            headers=key())).json()
    group_id = one["group_ids"][0]
    two = (await admin.post(f"{V}/print", json={"items": [{"part_id": part, "group": {"total": 3, "start_index": 2, "count": 1,
                                                                                     "group_id": group_id}}]}, headers=key())).json()
    assert two["group_ids"] == [group_id] and two["jobs"][0]["labels"][0]["group_index"] == 2
    r = await admin.post(f"{V}/print", json={"items": [{"part_id": part, "group": {"total": 3, "start_index": 3, "count": 2}}]},
                         headers=key())
    assert r.status_code == 422
    async with sessionmaker()() as db:
        assert (await db.execute(select(func.count()).select_from(LabelGroup))).scalar() == 2


async def test_required_print_time_value(admin: httpx.AsyncClient, ready: dict[str, Any]) -> None:
    spec = {"fields": fields("part_number") + [{"key": "manual.lot", "role": "detail", "uppercase": False, "caption": "LOT"}],
            "manual_fields": [{"key": "lot", "label": "Lot number", "type": "text", "max_length": 10, "required": True}],
            "style": STYLE}
    await admin.post(f"{V}/configs", json={"scope": "part", "part_id": ready["plain"]["id"], "label_size_id": ready["sizes"]["Large"],
                                           "spec": spec, "qr_mode": "none", "serial_mode": "none"})
    r = await admin.post(f"{V}/print", json={"items": [{"part_id": ready["plain"]["id"]}]}, headers=key())
    assert r.status_code == 422 and r.json()["error"]["message"] == "Enter Lot number to print."
    r = await admin.post(f"{V}/print", json={"items": [{"part_id": ready["plain"]["id"], "manual_values": {"lot": "L-1"}}]},
                         headers=key())
    assert r.status_code == 200
    async with sessionmaker()() as db:
        assert (await db.execute(select(func.count()).select_from(IssuedSerial))).scalar() == 0  # no serials on this label


async def test_large_batch_splits_into_jobs(admin: httpx.AsyncClient, ready: dict[str, Any]) -> None:
    items = [{"part_id": ready["part"]["id"], "quantity": 150}, {"part_id": ready["part"]["id"], "quantity": 100}]
    out = (await admin.post(f"{V}/print", json={"items": items}, headers=key())).json()
    assert [len(j["labels"]) for j in out["jobs"]] == [200, 50]
    assert len(set(out["serials"])) == 250
    async with sessionmaker()() as db:
        jobs = (await db.execute(select(PrintJob).order_by(PrintJob.seq_in_request))).scalars().all()
        assert [j.seq_in_request for j in jobs] == [1, 2] and jobs[0].payload_zpl.count(b"^XA") == 200


async def test_agent_claims_and_reports(admin: httpx.AsyncClient, ready: dict[str, Any], new_client: Any) -> None:
    agent = new_client()
    h = agent_headers(ready["token"])
    assert (await agent.get(f"{V}/agent/jobs/next", headers=h)).status_code == 204
    out = (await admin.post(f"{V}/print", json={"items": [{"part_id": ready["part"]["id"], "quantity": 2}]}, headers=key())).json()
    job_id = out["jobs"][0]["id"]
    r = await agent.get(f"{V}/agent/jobs/next", headers=h)
    assert r.status_code == 200 and r.json()["id"] == job_id and r.json()["zpl"].startswith("^XA\n^MNY\n")
    assert (await admin.get(f"{V}/jobs/{job_id}")).json()["status"] == "sending"
    assert (await admin.post(f"{V}/jobs/{job_id}/cancel")).json()["error"]["message"] == "This job has already been sent to the printer."
    assert (await agent.post(f"{V}/agent/jobs/{job_id}/status", json={"status": "sent"}, headers=h)).status_code == 204
    job = (await admin.get(f"{V}/jobs/{job_id}")).json()
    assert job["status"] == "sent" and job["sent_at"]
    async with sessionmaker()() as db:
        statuses = set((await db.execute(select(IssuedSerial.status))).scalars())
        assert statuses == {"printed"}
    r = await agent.post(f"{V}/agent/jobs/{job_id}/status", json={"status": "failed", "error": "late"}, headers=h)
    assert r.status_code == 409
    r = await agent.post(f"{V}/agent/jobs/{job_id}/status", json={"status": "confirmed"}, headers=h)
    assert r.status_code == 204 and (await admin.get(f"{V}/jobs/{job_id}")).json()["status"] == "confirmed"

    # Failure path: serials become unconfirmed; the error text is kept.
    out = (await admin.post(f"{V}/print", json={"items": [{"part_id": ready["part"]["id"]}]}, headers=key())).json()
    job2 = (await agent.get(f"{V}/agent/jobs/next", headers=h)).json()["id"]
    await agent.post(f"{V}/agent/jobs/{job2}/status", json={"status": "failed", "error": "USB write timed out"}, headers=h)
    assert (await admin.get(f"{V}/jobs/{job2}")).json()["error"] == "USB write timed out"
    async with sessionmaker()() as db:
        assert (await db.get(IssuedSerial, out["serials"][0])).status == "unconfirmed"  # type: ignore[union-attr]


async def test_agent_auth_boundaries(admin: httpx.AsyncClient, ready: dict[str, Any], new_client: Any) -> None:
    agent = new_client()
    h = agent_headers(ready["token"])
    assert (await admin.get(f"{V}/agent/jobs/next")).status_code == 403  # a user session can't act as the agent
    assert (await agent.get(f"{V}/agent/jobs/next", headers={"Authorization": "Bearer wrong"})).status_code == 403
    assert (await agent.get(f"{V}/parts", headers=h)).status_code == 401  # agent tokens only reach /agent/*
    r = await agent.post(f"{V}/agent/heartbeat", json={"printer_status": "out_of_media", "host_info": {"hostname": "LAPTOP"}},
                         headers=h)
    assert r.status_code == 204
    printer = (await admin.get(f"{V}/printers/{ready['printer_id']}")).json()
    assert printer["status"] == "out_of_media" and printer["agent_last_seen_at"]
    # Rotating the token invalidates the old one immediately.
    new = (await admin.post(f"{V}/printers/{ready['printer_id']}/agent-token")).json()["agent_token"]
    assert (await agent.get(f"{V}/agent/jobs/next", headers=h)).status_code == 403
    assert (await agent.get(f"{V}/agent/jobs/next", headers=agent_headers(new))).status_code == 204


async def test_lease_expiry_and_cancel(admin: httpx.AsyncClient, ready: dict[str, Any], new_client: Any) -> None:
    agent = new_client()
    h = agent_headers(ready["token"])
    out = (await admin.post(f"{V}/print", json={"items": [{"part_id": ready["part"]["id"]}]}, headers=key())).json()
    job_id = (await agent.get(f"{V}/agent/jobs/next", headers=h)).json()["id"]
    async with sessionmaker()() as db:
        await db.execute(text("UPDATE print_job SET claimed_at = now() - interval '61 seconds' WHERE id = :j"), {"j": job_id})
        await db.commit()
        await expire_leases(db)
        await db.commit()
    job = (await admin.get(f"{V}/jobs/{job_id}")).json()
    assert job["status"] == "failed" and job["error"] == "The print agent on the laptop isn't responding."
    async with sessionmaker()() as db:
        assert (await db.get(IssuedSerial, out["serials"][0])).status == "unconfirmed"  # type: ignore[union-attr]

    queued = (await admin.post(f"{V}/print", json={"items": [{"part_id": ready["part"]["id"]}]}, headers=key())).json()
    r = await admin.post(f"{V}/jobs/{queued['jobs'][0]['id']}/cancel")
    assert r.json()["status"] == "cancelled"
    async with sessionmaker()() as db:
        s = await db.get(IssuedSerial, queued["serials"][0])
        assert s is not None and s.status == "voided" and s.void_reason == "Cancelled before printing"


async def test_operator_can_print(operator: httpx.AsyncClient, ready: dict[str, Any]) -> None:
    r = await operator.post(f"{V}/print", json={"items": [{"part_id": ready["plain"]["id"]}]}, headers=key())
    assert r.status_code == 200 and r.json()["jobs"][0]["status"] == "queued"


# ---------------------------------------------------------------- serial safety (16.1, A3)
async def test_twenty_concurrent_allocations(ready: dict[str, Any]) -> None:
    """16.1: 20 concurrent allocate_serials calls of 50 each produce 1,000 distinct consecutive serials."""
    async with sessionmaker()() as db:
        seq = (await db.execute(select(SerialSequence))).scalar_one()
        part_id = uuid.UUID(ready["part"]["id"])
        user_id = (await db.execute(text("SELECT id FROM app_user LIMIT 1"))).scalar_one()
    start = seq.next_value

    async def allocate() -> list[str]:
        async with sessionmaker()() as db:
            rows = await db.execute(text("SELECT allocate_serials(:s, :p, 50, :u)"), {"s": seq.id, "p": part_id, "u": user_id})
            values = list(rows.scalars())
            await asyncio.sleep(0.01)  # hold the transaction open briefly so callers really overlap
            await db.commit()
            return values

    batches = await asyncio.gather(*[allocate() for _ in range(20)])
    everything = [v for b in batches for v in b]
    assert len(everything) == len(set(everything)) == 1000
    numbers = sorted(int(v.split("-")[1]) for v in everything)
    assert numbers == list(range(start, start + 1000))
    for b in batches:  # each call got one consecutive run
        nums = [int(v.split("-")[1]) for v in b]
        assert nums == list(range(nums[0], nums[0] + 50))


async def test_rolled_back_allocation_leaves_no_gap(ready: dict[str, Any]) -> None:
    """16.1: a rolled-back transaction leaves no gap and no rows."""
    async with sessionmaker()() as db:
        seq = (await db.execute(select(SerialSequence))).scalar_one()
        user_id = (await db.execute(text("SELECT id FROM app_user LIMIT 1"))).scalar_one()
        before = seq.next_value
        await db.execute(text("SELECT allocate_serials(:s, :p, 5, :u)"), {"s": seq.id, "p": uuid.UUID(ready["part"]["id"]), "u": user_id})
        await db.rollback()
    async with sessionmaker()() as db:
        assert (await db.execute(select(SerialSequence.next_value))).scalar_one() == before
        assert (await db.execute(select(func.count()).select_from(IssuedSerial))).scalar() == 0


async def test_a3_two_browsers_twenty_each(admin: httpx.AsyncClient, operator: httpx.AsyncClient, ready: dict[str, Any]) -> None:
    """A3: two browsers printing 20 labels each at the same time: 40 unique serials, no gaps."""
    body = {"items": [{"part_id": ready["part"]["id"], "quantity": 20}]}
    a, b = await asyncio.gather(admin.post(f"{V}/print", json=body, headers=key()),
                                operator.post(f"{V}/print", json=body, headers=key()))
    assert a.status_code == b.status_code == 200, (a.text, b.text)
    serials = a.json()["serials"] + b.json()["serials"]
    assert len(set(serials)) == 40
    assert sorted(int(re.sub(r"\D", "", s)) for s in serials) == list(range(1, 41))


async def test_concurrent_same_idempotency_key(admin: httpx.AsyncClient, new_client: Any, ready: dict[str, Any]) -> None:
    headers = key()
    body = {"items": [{"part_id": ready["plain"]["id"]}]}
    r1, r2 = await asyncio.gather(admin.post(f"{V}/print", json=body, headers=headers),
                                  admin.post(f"{V}/print", json=body, headers=headers))
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["request_id"] == r2.json()["request_id"]
    async with sessionmaker()() as db:
        assert (await db.execute(select(func.count()).select_from(PrintJob))).scalar() == 1


@pytest.mark.skip(reason="needs hardware")
def test_a2_qr_scans_on_every_preset() -> None:
    """A2: phone camera reads PN: and SN: payloads on every preset size."""


@pytest.mark.skip(reason="needs hardware")
def test_a5_box_set_on_the_printer() -> None:
    """A5: "Print all 3 boxes" gives BOX 1/3, 2/3, 3/3 with 3 distinct serials on real labels."""


@pytest.mark.skip(reason="needs hardware")
def test_a9_unplug_usb_goes_offline() -> None:
    """A9: unplug USB → status Offline within 40 s; Print disabled with PRINTER_OFFLINE message."""


@pytest.mark.skip(reason="needs hardware")
def test_a11_offset_shifts_test_label() -> None:
    """A11: +10 dot X offset visibly shifts the test label ~1.25 mm."""
