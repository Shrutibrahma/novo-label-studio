"""House label style (v1.1 U1, D21): renderer goldens, title fitting, footer rules, and the Label style API.

Goldens: 4 preset sizes × {band on, off} × {footer on, off} × {qr_side, grid (bin template)}, committed in
tests/goldens/house_goldens.json with the PNGs in tests/goldens/png/house-*.png. To update them deliberately:
UPDATE_GOLDENS=1 uv run pytest tests/test_house_style.py"""

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

from app.configs.presets import grid_template
from app.configs.spec import LabelSpec
from app.render.engine import RenderConfig, RenderResult, RenderSize, render
from app.render.house import TITLE_MIN_PT, HouseStyle, fit_title, snapshot_style
from tests.test_render import GOLDEN_DIR, LABELS, PRINTER, SIZES, SNAPSHOT, spec

V = "/api/v1"
HOUSE_GOLDEN_FILE = GOLDEN_DIR / "house_goldens.json"
BIN_FIELDS = [("bin_qty", "Bin qty"), ("bin_type", "Bin type"), ("station", "Station"),
              ("supermarket_bin", "Supermarket bin")]
GRID_LABELS = LABELS | dict(BIN_FIELDS)
GRID_SNAPSHOT: dict[str, Any] = {
    "part": {"part_number": "400278", "part_name": "Hex Bolt M8 x 40", "bin_qty": 300, "bin_type": "S",
             "station": "P2", "supermarket_bin": "SD-1-A"},
    "manual": {},
    "generated": {"serial": "NOVO-00001843", "print_date": "2026-10-30", "qr_payload": "PN:400278"},
}


def house(**over: Any) -> dict[str, Any]:
    return snapshot_style(HouseStyle.model_validate(over), "Bin label", "Novo Precision")


def bin_grid_spec() -> LabelSpec:
    return LabelSpec.model_validate({"fields": [], "style": {"layout": "grid"},
                                     "grid": grid_template("bin", BIN_FIELDS)})


def draw(s: LabelSpec, snapshot: dict[str, Any], size: tuple[str, str], qr: str, hs: dict[str, Any] | None,
         labels: dict[str, str] = LABELS) -> RenderResult:
    snap = copy.deepcopy(snapshot)
    if hs is not None:
        snap["generated"]["house_style"] = hs
    return render(snap, RenderConfig(spec=s, qr_mode=qr, field_labels=labels),
                  RenderSize(Decimal(size[0]), Decimal(size[1])), PRINTER)


def house_cases() -> list[tuple[str, LabelSpec, dict[str, Any], tuple[str, str], str, dict[str, Any], dict[str, str]]]:
    cases = []
    for size_name, size in SIZES.items():
        for band in (True, False):
            for footer in (True, False):
                hs = house(title_band=band, footer=footer)
                tag = f"{size_name}-band_{'on' if band else 'off'}-footer_{'on' if footer else 'off'}"
                cases.append((f"house-qr_side-{tag}", spec(), SNAPSHOT, size, "serial", hs, LABELS))
                cases.append((f"house-grid-{tag}", bin_grid_spec(), GRID_SNAPSHOT, size, "part", hs, GRID_LABELS))
    return cases


def test_house_goldens() -> None:
    updating = os.environ.get("UPDATE_GOLDENS") == "1"
    stored: dict[str, str] = json.loads(HOUSE_GOLDEN_FILE.read_text()) if HOUSE_GOLDEN_FILE.exists() else {}
    got: dict[str, str] = {}
    for case_id, s, snap, size, qr, hs, labels in house_cases():
        result = draw(s, snap, size, qr, hs, labels)
        got[case_id] = result.sha256.hex()
        if updating:
            (GOLDEN_DIR / "png" / f"{case_id}.png").write_bytes(result.png)
    if updating:
        HOUSE_GOLDEN_FILE.write_text(json.dumps(got, indent=2, sort_keys=True) + "\n")
        pytest.skip("goldens updated")
    assert got == stored, "house style output changed; review tests/goldens/png/house-* and rerun with UPDATE_GOLDENS=1"


def test_without_house_style_renders_as_v1() -> None:
    """Snapshots printed before v1.1 have no generated.house_style and must re-render exactly as before."""
    plain = draw(spec(), SNAPSHOT, SIZES["large"], "serial", None)
    assert plain.house is None
    styled = draw(spec(), SNAPSHOT, SIZES["large"], "serial", house())
    assert styled.house is not None and styled.png != plain.png


def test_house_font_replaces_the_design_font() -> None:
    a = draw(spec("roboto_condensed", primary_weight="regular"), SNAPSHOT, SIZES["large"], "serial", house())
    b = draw(spec("inter"), SNAPSHOT, SIZES["large"], "serial", house())
    assert a.png == b.png  # style.font and primary_weight are ignored
    c = draw(spec("inter"), SNAPSHOT, SIZES["large"], "serial", house(font="atkinson"))
    assert c.png != b.png


def test_compact_labels_show_the_frame_only() -> None:
    r = draw(bin_grid_spec(), GRID_SNAPSHOT, SIZES["small"], "part", house())
    assert r.house is not None and r.house.frame == 4 and r.house.band is None and r.house.footer_rule is None
    big = draw(bin_grid_spec(), GRID_SNAPSHOT, SIZES["medium"], "part", house())
    assert big.house is not None and big.house.band is not None and big.house.footer_rule is not None


def test_footer_leaves_out_what_the_design_prints() -> None:
    # spec() prints the serial; print_date isn't on it -> footer shows the date only.
    r = draw(spec(), SNAPSHOT, SIZES["large"], "serial", house())
    assert r.house is not None and r.house.footer_rule is not None
    fields = [{"key": "part_number", "role": "primary", "uppercase": False, "caption": None},
              {"key": "serial", "role": "secondary", "uppercase": False, "caption": None},
              {"key": "print_date", "role": "detail", "uppercase": False, "caption": None}]
    both = draw(spec(fields=fields), SNAPSHOT, SIZES["large"], "serial", house())
    assert both.house is not None and both.house.footer_rule is None  # nothing left for the footer
    no_serial = copy.deepcopy(SNAPSHOT)
    del no_serial["generated"]["serial"]
    only_pn = draw(spec(fields=fields[:1]), no_serial, SIZES["large"], "none", house())
    assert only_pn.house is not None and only_pn.house.footer_rule is not None  # date only


def test_bin_layout_title_moves_into_the_band() -> None:
    s = LabelSpec.model_validate({"fields": [], "style": {"layout": "bin"},
                                  "bin": {"title": "COLT BIN ID", "info1": {"key": "bin_qty", "heading": "BIN QTY"}}})
    banded = draw(s, GRID_SNAPSHOT, SIZES["large"], "part", house() | {"title": "COLT BIN ID"}, GRID_LABELS)
    assert banded.fits, banded.warnings
    unbanded = draw(s, GRID_SNAPSHOT, SIZES["large"], "part", house(title_band=False), GRID_LABELS)
    assert unbanded.fits and unbanded.png != banded.png


def test_long_title_shrinks_then_clips_never_overflows() -> None:
    title = "WORKSTATION SAFETY NOTICE"[:24]
    assert len(title) == 24
    # A 2 in wide Standard label: content box 406 - 2*13 - 2*4 frame = 372 dots, 8 dots padding each side.
    pt, shown = fit_title(title, "inter", 203, 372 - 16)
    assert TITLE_MIN_PT <= pt <= 10 and title.startswith(shown) and shown
    tiny_pt, tiny = fit_title(title, "inter", 203, 120)
    assert tiny_pt == TITLE_MIN_PT and len(tiny) < len(title) and title.startswith(tiny)
    # Drawn on a 2 × 2 in label: nothing escapes the band or the frame.
    r = draw(spec(), SNAPSHOT, ("2.00", "2.00"), "none", snapshot_style(HouseStyle(), title, "Novo Precision"))
    assert r.house is not None and r.house.band is not None
    img = Image.open(io.BytesIO(r.png))
    top, height = r.house.band
    m = 13
    for y in range(top, top + height):
        assert img.getpixel((m + 4, y)) == 0 and img.getpixel((img.width - m - 5, y)) == 0  # band ends stay black


# ---------------------------------------------------------------- API
async def test_label_style_api(admin: httpx.AsyncClient, operator: httpx.AsyncClient) -> None:
    r = await operator.get(f"{V}/settings/label-style")
    assert r.status_code == 200 and r.json() == HouseStyle().model_dump()
    new = {"font": "atkinson", "frame": True, "title_band": False, "company_in_band": True, "footer": True,
           "title_in_band": False}
    assert (await operator.put(f"{V}/settings/label-style", json=new)).status_code == 403
    r = await admin.put(f"{V}/settings/label-style", json={**new, "font": "comic_sans"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "CONFIG_INVALID"
    r = await admin.put(f"{V}/settings/label-style", json={**new, "extra": 1})
    assert r.status_code == 422 and r.json()["error"]["code"] == "CONFIG_INVALID"
    r = await admin.put(f"{V}/settings/label-style", json=new)
    assert r.status_code == 200 and r.json() == new
    assert (await operator.get(f"{V}/settings/label-style")).json() == new


async def test_preview_draft_style_is_admin_only_and_titles(admin: httpx.AsyncClient,
                                                            operator: httpx.AsyncClient) -> None:
    part = (await admin.post(f"{V}/parts", json={"part_number": "T-1", "part_name": "Styled part"})).json()
    draft = {"font": "inter", "frame": True, "title_band": True, "company_in_band": False, "footer": False,
             "title_in_band": True}
    body = {"part_id": part["id"], "house_style": draft}
    assert (await operator.post(f"{V}/render/preview", json=body)).status_code == 403
    first = await admin.post(f"{V}/render/preview", json=body)
    assert first.status_code == 200, first.text
    assert len(first.json()["layout_box"]) == 4
    types = (await admin.get(f"{V}/label-types")).json()
    assert types[0]["title"] is None
    r = await admin.patch(f"{V}/label-types/{types[0]['id']}", json={"title": "  Part tag  "})
    assert r.status_code == 200 and r.json()["title"] == "Part tag"
    second = await admin.post(f"{V}/render/preview", json=body)
    assert second.json()["png_base64"] != first.json()["png_base64"]  # the band shows the new title
    r = await admin.patch(f"{V}/label-types/{types[0]['id']}", json={"title": "X" * 25})
    assert r.status_code == 422 and r.json()["error"]["code"] == "FIELD_TOO_LONG"
    r = await admin.patch(f"{V}/label-types/{types[0]['id']}", json={"title": None})
    assert r.status_code == 200 and r.json()["title"] is None


async def test_band_shows_only_the_company_by_default(admin: httpx.AsyncClient) -> None:
    """Owner's request 2026-10-30: no "LABEL" / "KANBAN" in the band, just the (editable) company name."""
    part = (await admin.post(f"{V}/parts", json={"part_number": "T-2", "part_name": "Band part"})).json()
    style = {"font": "inter", "frame": True, "title_band": True, "company_in_band": True, "footer": False}
    plain = await admin.post(f"{V}/render/preview", json={"part_id": part["id"], "house_style": style})
    named = await admin.post(f"{V}/render/preview", json={"part_id": part["id"],
                                                          "house_style": style | {"title_in_band": True}})
    assert plain.status_code == named.status_code == 200
    assert plain.json()["png_base64"] != named.json()["png_base64"]
    await admin.patch(f"{V}/settings", json={"company_name": "Novo Lean Solutions"})
    renamed = await admin.post(f"{V}/render/preview", json={"part_id": part["id"], "house_style": style})
    assert renamed.json()["png_base64"] != plain.json()["png_base64"]
