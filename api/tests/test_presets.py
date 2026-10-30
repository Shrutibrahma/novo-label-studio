"""Industrial presets and box options (v1.1 U3, D22, D23): goldens of every preset at its preset size, the
white-on-black and arrow boxes, and creating label types from presets.

Goldens: tests/goldens/preset_goldens.json + png/preset-*.png. Update deliberately:
UPDATE_GOLDENS=1 uv run pytest tests/test_presets.py"""

from __future__ import annotations

import copy
import io
import json
import os
from decimal import Decimal
from typing import Any

import httpx
import pytest
from PIL import Image

from app.configs.presets import PRESETS, Preset, preset_spec
from app.configs.spec import LabelSpec, validate_spec
from app.errors import ApiError
from app.render.engine import RenderConfig, RenderResult, RenderSize, render
from app.render.house import HouseStyle, snapshot_style
from app.render.snapshot import build_snapshot, field_labels, part_field_values
from tests.test_render import GOLDEN_DIR, PRINTER, SIZES

V = "/api/v1"
PRESET_GOLDEN_FILE = GOLDEN_DIR / "preset_goldens.json"
CUSTOM = [("location", "Location"), ("process", "Process"), ("lot_size", "Lot size"), ("min", "Min"),
          ("max", "Max"), ("bin_qty", "Bin qty"), ("bin_type", "Bin type"), ("station", "Station")]
PART_VALUES = part_field_values("NP-10421", "Bearing Housing", None, "C",
                                {"location": "A-12-03", "process": "CNC", "lot_size": 50, "min": 2, "max": 6,
                                 "bin_qty": 25, "bin_type": "S", "station": "P2"}, "10-32 x 1/2 16")
MANUAL: dict[str, dict[str, Any]] = {
    "kanban": {"card": {"index": 1, "total": 2}},
    "quality": {"status": "HOLD", "reason": "Burr on bore, check with QE"},
    "box": {"qty": 24, "box": {"index": 2, "total": 4}},
    "workstation": {"station": "CELL 4", "note": "Torque check every 2 hours"},
}
PRESET_SIZE = {"Large": SIZES["large"], "Tall": SIZES["tall"]}


def preset_label(p: Preset, hs: HouseStyle | None = None) -> RenderResult:
    s = LabelSpec.model_validate(preset_spec(p, CUSTOM))
    labels = field_labels(s, dict(CUSTOM))
    serial = "NOVO-00001843" if p.serial_mode == "required" else None
    snap = build_snapshot(s, p.qr_mode, PART_VALUES, {k for k, _ in CUSTOM}, copy.deepcopy(MANUAL.get(p.key, {})),
                          serial, "2026-10-30", labels, snapshot_style(hs or HouseStyle(), p.name, "Novo Precision"))
    if p.kind == "quick":
        snap["part"] = {}
    size = PRESET_SIZE[p.size_name]
    return render(snap, RenderConfig(spec=s, qr_mode=p.qr_mode, field_labels=labels),
                  RenderSize(Decimal(size[0]), Decimal(size[1])), PRINTER)


def test_preset_goldens() -> None:
    updating = os.environ.get("UPDATE_GOLDENS") == "1"
    stored: dict[str, str] = json.loads(PRESET_GOLDEN_FILE.read_text()) if PRESET_GOLDEN_FILE.exists() else {}
    got: dict[str, str] = {}
    for p in PRESETS:
        r = preset_label(p)
        assert r.fits, (p.key, r.warnings)
        got[f"preset-{p.key}"] = r.sha256.hex()
        if updating:
            (GOLDEN_DIR / "png" / f"preset-{p.key}.png").write_bytes(r.png)
    if updating:
        PRESET_GOLDEN_FILE.write_text(json.dumps(got, indent=2, sort_keys=True) + "\n")
        pytest.skip("goldens updated")
    assert got == stored, "preset output changed; review tests/goldens/png/preset-* and rerun with UPDATE_GOLDENS=1"


def test_presets_follow_the_look_rules() -> None:
    """6.3: one xl box at most; headings are uppercase nouns of at most 14 characters."""
    for p in PRESETS:
        cells = [c for r in preset_spec(p, CUSTOM)["grid"]["rows"] for c in r["cells"]]
        assert sum(c["size"] == "xl" for c in cells) <= 1, p.key
        for c in cells:
            if c["heading"]:
                assert c["heading"] == c["heading"].upper() and len(c["heading"]) <= 14, (p.key, c["heading"])


def grid(cells: list[dict[str, Any]]) -> LabelSpec:
    return LabelSpec.model_validate({"fields": [], "style": {"layout": "grid"},
                                     "grid": {"rows": [{"height": 1, "cells": cells}]}})


def draw(s: LabelSpec, qr: str = "none") -> RenderResult:
    snap = {"part": {"part_number": "NP-10421"}, "manual": {},
            "generated": {"print_date": "2026-10-30", "qr_payload": "PN:NP-10421"}}
    return render(snap, RenderConfig(spec=s, qr_mode=qr, field_labels={}),
                  RenderSize(Decimal("4.00"), Decimal("2.00")), PRINTER)


def dark_share(r: RenderResult, box: tuple[int, int, int, int]) -> float:
    img = Image.open(io.BytesIO(r.png)).convert("L").crop(box)
    return img.tobytes().count(0) / (img.width * img.height)


def test_invert_and_arrow() -> None:
    plain = draw(grid([{"kind": "field", "key": "part_number"}]))
    inverted = draw(grid([{"kind": "field", "key": "part_number", "invert": True}]))
    assert dark_share(plain, (30, 30, 780, 380)) < 0.3 < 0.7 < dark_share(inverted, (30, 30, 780, 380))
    up = draw(grid([{"kind": "arrow", "direction": "up"}]))
    down = draw(grid([{"kind": "arrow", "direction": "down"}]))
    assert up.fits and up.png != down.png
    # Arrow area: 70 % of the smaller inner side, squared, halved (a triangle).
    assert 0.08 < dark_share(up, (13, 13, 799, 393)) < 0.2
    white_arrow = draw(grid([{"kind": "arrow", "direction": "up", "invert": True}]))
    assert dark_share(white_arrow, (13, 13, 799, 393)) > 0.8
    # QR boxes ignore invert.
    assert draw(grid([{"kind": "qr", "invert": True}]), "part").png == draw(grid([{"kind": "qr"}]), "part").png


def test_box_option_validation() -> None:
    with pytest.raises(ApiError) as err:
        from app.configs.spec import parse_spec
        parse_spec({"style": {"layout": "grid"}, "grid": {"rows": [{"cells": [{"kind": "arrow", "direction": "sideways"}]}]}})
    assert err.value.code == "CONFIG_INVALID"
    validate_spec(grid([{"kind": "qr", "invert": True}]), set(), "part", "none")  # accepted, ignored


async def test_new_type_from_each_preset(admin: httpx.AsyncClient) -> None:
    presets = (await admin.get(f"{V}/label-types/presets")).json()
    assert [p["key"] for p in presets][:6] == ["part", "bin", "kanban", "rack", "quality", "box"]
    part = (await admin.post(f"{V}/parts", json={"part_number": "NP-10421", "part_name": "Bearing Housing",
                                                 "revision": "C"})).json()
    for p in presets:
        if p["kind"] != "part":
            continue
        r = await admin.post(f"{V}/label-types", json={"name": p["name"], "preset": p["key"]})
        assert r.status_code == 201, r.text
        t = r.json()
        assert t["layout"] == "grid" and t["size"]["name"] == p["size_name"]
        manual = MANUAL.get(p["key"], {})
        prev = (await admin.post(f"{V}/render/preview", json={"part_id": part["id"], "label_type_id": t["id"],
                                                              "manual_values": manual})).json()
        assert prev["fits"], (p["key"], prev["warnings"])
    assert (await admin.post(f"{V}/label-types", json={"name": "X", "preset": "nope"})).status_code == 404
