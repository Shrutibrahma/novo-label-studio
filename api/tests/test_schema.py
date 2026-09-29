"""Section 16.1 'Schema': loads cleanly on Postgres 16; triggers reject config mutation, printed_label
update/delete, reprint mismatch, alias collisions, group index > total."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import sessionmaker
from tests.conftest import insert_user


async def q(sql: str, **params: Any) -> Any:
    async with sessionmaker()() as db:
        res = await db.execute(text(sql), params)
        value = res.scalar() if res.returns_rows else None
        await db.commit()
        return value


async def fails(sql: str, match: str, **params: Any) -> None:
    async with sessionmaker()() as db:
        with pytest.raises(DBAPIError, match=match):
            await db.execute(text(sql), params)
        await db.rollback()


@pytest.fixture
async def base() -> dict[str, uuid.UUID]:
    uid = await insert_user("root", "admin")
    size = await q("INSERT INTO label_size (name, width_in, height_in) VALUES ('Large', 4, 2) RETURNING id")
    part = await q("INSERT INTO part (part_number, part_name, created_by, updated_by) "
                   "VALUES ('NP-10421', 'Bearing Housing', :u, :u) RETURNING id", u=uid)
    other = await q("INSERT INTO part (part_number, part_name, created_by, updated_by) "
                    "VALUES ('NP-20000', 'Other', :u, :u) RETURNING id", u=uid)
    cfg = await q("INSERT INTO label_config (config_key, version, scope, label_size_id, spec, created_by) "
                  "VALUES (gen_random_uuid(), 1, 'default', :s, '{}', :u) RETURNING id", s=size, u=uid)
    agent = await q("INSERT INTO print_agent (name, token_hash) VALUES ('a', 'x') RETURNING id")
    printer = await q("INSERT INTO printer (name, model, print_method, dpi, print_width_in, media_min_width_in, "
                      "media_max_width_in, agent_id) VALUES ('p', 'Zebra ZQ630 Plus', 'direct_thermal', 203, "
                      "4.1, 2, 4.4, :a) RETURNING id", a=agent)
    req = await q("INSERT INTO print_request (idempotency_key, kind, request_body, created_by) "
                  "VALUES (gen_random_uuid(), 'print', '{}', :u) RETURNING id", u=uid)
    job = await q("INSERT INTO print_job (request_id, seq_in_request, printer_id, kind, payload_zpl, created_by) "
                  "VALUES (:r, 1, :p, 'print', '\\x5e5841'::bytea, :u) RETURNING id", r=req, p=printer, u=uid)
    return {"user": uid, "size": size, "part": part, "other": other, "config": cfg, "printer": printer,
            "job": job, "request": req}


async def insert_label(b: dict[str, uuid.UUID], seq: int, snapshot: str = '{"part": {"part_number": "NP-10421"}}',
                       reprint_of: uuid.UUID | None = None, part: uuid.UUID | None = None,
                       group: uuid.UUID | None = None, group_index: int | None = None) -> Any:
    return await q(
        "INSERT INTO printed_label (job_id, seq_in_job, part_id, label_config_id, snapshot, dpi, bitmap_png, "
        "bitmap_sha256, reprint_of, group_id, group_index) VALUES (:j, :s, :p, :c, CAST(:snap AS jsonb), 203, "
        "'\\x00'::bytea, '\\x00'::bytea, :r, :g, :gi) RETURNING id",
        j=b["job"], s=seq, p=part or b["part"], c=b["config"], snap=snapshot, r=reprint_of, g=group, gi=group_index)


async def test_schema_objects_exist(base: dict[str, uuid.UUID]) -> None:
    n = await q("SELECT count(*) FROM information_schema.tables WHERE table_schema='public' "
                "AND table_type='BASE TABLE' AND table_name <> 'alembic_version'")
    assert n == 21
    assert await q("SELECT count(*) FROM part_label_freshness") == 2
    assert await q("SELECT normalize_alias('10-32 X 1/2  16')") == "10 32 x 1/2 16"


async def test_label_config_is_immutable(base: dict[str, uuid.UUID]) -> None:
    await fails("UPDATE label_config SET version = 2 WHERE id = :c", "immutable", c=base["config"])
    await fails("UPDATE label_config SET spec = '{\"x\": 1}' WHERE id = :c", "immutable", c=base["config"])
    # Retiring is the one allowed change; un-retiring is not.
    await q("UPDATE label_config SET is_current = false WHERE id = :c", c=base["config"])
    await fails("UPDATE label_config SET is_current = true WHERE id = :c", "immutable", c=base["config"])


async def test_printed_label_update_and_delete_rejected(base: dict[str, uuid.UUID]) -> None:
    label = await insert_label(base, 1)
    await fails("UPDATE printed_label SET copies = 2 WHERE id = :l", "immutable", l=label)
    await fails("DELETE FROM printed_label WHERE id = :l", "immutable", l=label)


async def test_reprint_must_match_original(base: dict[str, uuid.UUID]) -> None:
    original = await insert_label(base, 1)
    await insert_label(base, 2, reprint_of=original)  # same snapshot: allowed
    async with sessionmaker()() as db:
        with pytest.raises(DBAPIError, match="reprint must match"):
            await db.execute(text(
                "INSERT INTO printed_label (job_id, seq_in_job, part_id, label_config_id, snapshot, dpi, bitmap_png,"
                " bitmap_sha256, reprint_of) VALUES (:j, 3, :p, :c, '{\"part\": {\"part_number\": \"CHANGED\"}}',"
                " 203, '\\x00', '\\x00', :r)"),
                {"j": base["job"], "p": base["part"], "c": base["config"], "r": original})
        await db.rollback()
    await fails("INSERT INTO printed_label (job_id, seq_in_job, part_id, label_config_id, snapshot, dpi, bitmap_png,"
                " bitmap_sha256, reprint_of) VALUES (:j, 4, :p, :c, '{\"part\": {\"part_number\": \"NP-10421\"}}',"
                " 203, '\\x00', '\\x00', :r)", "reprint must match",
                j=base["job"], p=base["other"], c=base["config"], r=original)


async def test_alias_collisions(base: dict[str, uuid.UUID]) -> None:
    await q("INSERT INTO part_alias (part_id, alias, is_label_name, created_by) "
            "VALUES (:p, '10-32 x 1/2 16', true, :u)", p=base["part"], u=base["user"])
    # One alias -> one part: another spelling with the same normalization is rejected.
    await fails("INSERT INTO part_alias (part_id, alias, created_by) VALUES (:p, '10 32 X 1/2 16', :u)",
                "part_alias_norm_uq", p=base["other"], u=base["user"])
    # An alias can't be another part's part number.
    await fails("INSERT INTO part_alias (part_id, alias, created_by) VALUES (:p, 'np-20000', :u)",
                "another part's part number", p=base["part"], u=base["user"])
    # ...and a part number can't be another part's alias.
    await q("INSERT INTO part_alias (part_id, alias, created_by) VALUES (:p, 'BRG-HOUSING', :u)",
            p=base["part"], u=base["user"])
    await fails("INSERT INTO part (part_number, part_name, created_by, updated_by) "
                "VALUES ('brg-housing', 'X', :u, :u)", "already a label name", u=base["user"])
    await fails("UPDATE part SET part_number = 'BRG-HOUSING' WHERE id = :p", "already a label name",
                p=base["other"])
    # Only one label name per part.
    await fails("INSERT INTO part_alias (part_id, alias, is_label_name, created_by) VALUES (:p, 'Second', true, :u)",
                "part_alias_label_name_uq", p=base["part"], u=base["user"])


async def test_group_index_cannot_exceed_total(base: dict[str, uuid.UUID]) -> None:
    group = await q("INSERT INTO label_group (part_id, total, created_by) VALUES (:p, 3, :u) RETURNING id",
                    p=base["part"], u=base["user"])
    await insert_label(base, 1, group=group, group_index=3)
    await fails("INSERT INTO printed_label (job_id, seq_in_job, part_id, label_config_id, snapshot, dpi, bitmap_png,"
                " bitmap_sha256, group_id, group_index) VALUES (:j, 2, :p, :c, '{}', 203, '\\x00', '\\x00', :g, 4)",
                "exceeds group total", j=base["job"], p=base["part"], c=base["config"], g=group)


async def test_single_current_default_config(base: dict[str, uuid.UUID]) -> None:
    await fails("INSERT INTO label_config (config_key, version, scope, label_size_id, spec, created_by) "
                "VALUES (gen_random_uuid(), 1, 'default', :s, '{}', :u)", "label_config_current_default_uq",
                s=base["size"], u=base["user"])


async def test_serial_qr_needs_serial(base: dict[str, uuid.UUID]) -> None:
    await fails("INSERT INTO label_config (config_key, version, scope, part_id, label_size_id, spec, qr_mode, "
                "created_by) VALUES (gen_random_uuid(), 1, 'part', :p, :s, '{}', 'serial', :u)",
                "label_config_check", p=base["part"], s=base["size"], u=base["user"])
