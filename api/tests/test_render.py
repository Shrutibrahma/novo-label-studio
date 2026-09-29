"""Renderer tests (16.1): golden images, fit tests, and the 7.x rules they depend on.

Goldens: fixed inputs → byte-identical PNG sha256 for each layout family × each preset size × each font.
They are committed in tests/goldens/. To update them deliberately:  UPDATE_GOLDENS=1 uv run pytest tests/test_render.py
"""

from __future__ import annotations

import io
import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import segno
from PIL import Image

from app.configs.spec import LabelSpec
from app.render.canvas import SAFE_MARGIN_DOTS
from app.render.engine import RenderConfig, RenderPrinter, RenderSize, build_lines, render

GOLDEN_DIR = Path(__file__).parent / "goldens"
GOLDEN_FILE = GOLDEN_DIR / "render_goldens.json"
PRINTER = RenderPrinter(dpi=203, print_width_in=Decimal("4.100"))
SIZES = {"small": ("2.00", "1.00"), "medium": ("3.00", "2.00"), "large": ("4.00", "2.00"), "tall": ("4.00", "6.00")}
# qr_top never occurs on a preset (Tall is exactly H = 1.5 × W, which is qr_side), so a narrow tall custom size
# covers that family.
QR_TOP_SIZE = ("2.00", "4.00")
FONTS = ("inter", "roboto_condensed", "atkinson")
LABELS = {"label_name": "Label name", "part_number": "Part number", "part_name": "Part name",
          "description": "Description", "revision": "Revision", "serial": "Serial number", "print_date": "Print date",
          "manual.box": "Box"}

SNAPSHOT: dict[str, Any] = {
    "part": {"label_name": "10-32 x 1/2 16", "part_number": "NP-10421", "part_name": "Bearing Housing",
             "revision": "C"},
    "manual": {"box": {"index": 2, "total": 3}},
    "generated": {"serial": "NOVO-00001843", "print_date": "2026-09-29",
                  "qr_payload": "SN:NOVO-00001843|PN:NP-10421"},
}


def spec(font: str = "inter", fields: list[dict[str, Any]] | None = None, **style: Any) -> LabelSpec:
    return LabelSpec.model_validate({
        "fields": fields if fields is not None else [
            {"key": "label_name", "role": "primary", "uppercase": True, "caption": None},
            {"key": "part_number", "role": "secondary", "uppercase": True, "caption": "PN"},
            {"key": "serial", "role": "secondary", "uppercase": True, "caption": None},
            {"key": "revision", "role": "detail", "uppercase": True, "caption": "REV"},
            {"key": "manual.box", "role": "detail", "uppercase": True, "caption": None},
        ],
        "manual_fields": [{"key": "box", "label": "Box", "type": "box_sequence", "noun": "BOX", "required": True}],
        "style": {"font": font, "primary_weight": "bold", "alignment": "left", "emphasis": "medium",
                  "spacing": "standard", "qr_position": "right"} | style,
    })


def run(s: LabelSpec, size: tuple[str, str], qr: str = "none", snapshot: dict[str, Any] | None = None) -> Any:
    return render(snapshot or SNAPSHOT, RenderConfig(spec=s, qr_mode=qr, field_labels=LABELS),
                  RenderSize(Decimal(size[0]), Decimal(size[1])), PRINTER)


def golden_cases() -> list[tuple[str, LabelSpec, tuple[str, str], str]]:
    cases = []
    for font in FONTS:
        for size_name, size in SIZES.items():
            cases.append((f"stack-{size_name}-{font}", spec(font), size, "none"))
            cases.append((f"qr_side-{size_name}-{font}", spec(font), size, "serial"))
        cases.append((f"qr_top-2x4-{font}", spec(font), QR_TOP_SIZE, "part"))
    return cases


def test_render_goldens() -> None:
    updating = os.environ.get("UPDATE_GOLDENS") == "1"
    stored: dict[str, str] = json.loads(GOLDEN_FILE.read_text()) if GOLDEN_FILE.exists() else {}
    got: dict[str, str] = {}
    for case_id, s, size, qr in golden_cases():
        result = run(s, size, qr)
        assert result.family == case_id.split("-")[0], case_id
        assert result.fits, (case_id, result.warnings)
        got[case_id] = result.sha256.hex()
        if updating:
            (GOLDEN_DIR / "png").mkdir(parents=True, exist_ok=True)
            (GOLDEN_DIR / "png" / f"{case_id}.png").write_bytes(result.png)
    if updating:
        GOLDEN_FILE.write_text(json.dumps(got, indent=2, sort_keys=True) + "\n")
        pytest.skip("goldens updated")
    assert got == stored, "renderer output changed; review tests/goldens/png and rerun with UPDATE_GOLDENS=1"


def test_render_is_deterministic() -> None:
    a = run(spec(), SIZES["large"], "serial")
    b = run(spec(), SIZES["large"], "serial")
    assert a.png == b.png and a.sha256 == b.sha256


def test_canvas_is_one_bit_and_nothing_in_safe_margin() -> None:
    for size_name, size in SIZES.items():
        result = run(spec(), size, "serial")
        img = Image.open(io.BytesIO(result.png))
        assert img.mode == "1" and img.size == (result.width_dots, result.height_dots)
        w, h, m = img.size[0], img.size[1], SAFE_MARGIN_DOTS
        px = img.load()
        for x in range(w):
            for y in list(range(m)) + list(range(h - m, h)):
                assert px[x, y] != 0, (size_name, x, y)
        for y in range(h):
            for x in list(range(m)) + list(range(w - m, w)):
                assert px[x, y] != 0, (size_name, x, y)


def test_long_label_name_wraps_then_fails() -> None:
    """Fit test: a long label name wraps to 2 lines, then fails with TEXT_TOO_LONG."""
    fields = [{"key": "label_name", "role": "primary", "uppercase": False, "caption": None}]
    # Too wide for one line even at the 10 pt minimum (7.5 step 1), but fits on two (step 2).
    medium = {"part": {"label_name": "Heavy duty flanged bearing housing assembly with grease fittings"},
              "manual": {}, "generated": {}}
    result = run(spec(fields=fields), SIZES["large"], snapshot=medium)
    lines = build_lines(spec(fields=fields), medium)
    assert result.fits
    from app.render.engine import _fit_width  # the width pass alone, to see the wrap decision

    line = lines[0]
    _fit_width(line, 812 - 26, 203)
    assert len(line.parts) == 2 and not line.too_long

    long = {"part": {"label_name": "Heavy duty flanged bearing housing assembly with grease fittings, double lip "
                                   "seals and a cast iron base for conveyor drive shafts in wet areas"},
            "manual": {}, "generated": {}}
    result = run(spec(fields=fields), SIZES["large"], snapshot=long)
    assert not result.fits
    assert [(w.code, w.field) for w in result.warnings] == [("TEXT_TOO_LONG", "label_name")]
    assert result.warnings[0].message == '"Label name" is too long for this label size. Choose a larger size or a smaller text size.'


def test_detail_lines_never_wrap() -> None:
    fields = [{"key": "part_number", "role": "primary", "uppercase": False, "caption": None},
              {"key": "description", "role": "detail", "uppercase": False, "caption": None}]
    snap = {"part": {"part_number": "X", "description": "A very long description that cannot fit on a small label"},
            "manual": {}, "generated": {}}
    result = run(spec(fields=fields), SIZES["small"], snapshot=snap)
    assert [(w.code, w.field) for w in result.warnings] == [("TEXT_TOO_LONG", "description")]


def test_nine_fields_on_small_is_too_tall() -> None:
    """Fit test: 9 fields on Small fails with CONTENT_TOO_TALL."""
    keys = ["part_number", "part_name", "description", "revision", "label_name", "serial", "print_date",
            "manual.box", "extra"]
    fields = [{"key": k, "role": "primary" if i == 0 else "secondary" if i < 3 else "detail",
               "uppercase": False, "caption": None} for i, k in enumerate(keys)]
    snap = {"part": {"part_number": "NP-1", "part_name": "Nut", "description": "Hex", "revision": "A",
                     "label_name": "M6", "extra": "Zinc"},
            "manual": {"box": {"index": 1, "total": 2}},
            "generated": {"serial": "NOVO-00000001", "print_date": "2026-09-29"}}
    result = run(spec(fields=fields), SIZES["small"], snapshot=snap)
    assert not result.fits
    assert [w.code for w in result.warnings] == ["CONTENT_TOO_TALL"]
    assert result.warnings[0].message == "Too much information for this label size. Remove a field or choose a larger size."


@pytest.mark.parametrize("serial", ["NOVO-00000001", "NOVO-00000001-EXTRA-LONG-SERIAL-FOR-QR-VERSION"])
def test_qr_on_small_follows_module_math(serial: str) -> None:
    """Fit test: QR on Small with 3 text lines passes or fails exactly per 7.6 math."""
    payload = f"SN:{serial}|PN:NP-10421-LONG-PART-NUMBER-VALUE"
    fields = [{"key": "part_number", "role": "primary", "uppercase": False, "caption": None},
              {"key": "serial", "role": "secondary", "uppercase": False, "caption": None},
              {"key": "revision", "role": "detail", "uppercase": False, "caption": None}]
    snap = {"part": {"part_number": "NP-1", "revision": "A"}, "manual": {},
            "generated": {"serial": "S-1", "qr_payload": payload}}
    result = run(spec(fields=fields), SIZES["small"], "serial", snap)
    content_w, content_h = 406 - 26, 203 - 26
    side = min(content_h, content_w * 2 // 5)
    modules = segno.make(payload, error="m", boost_error=False, micro=False).symbol_size(border=0)[0]
    module_dots = side // (modules + 8)
    codes = [w.code for w in result.warnings]
    if module_dots < 3:
        assert "QR_TOO_SMALL" in codes and not result.fits
    else:
        assert "QR_TOO_SMALL" not in codes


def test_qr_payload_too_long() -> None:
    snap = {"part": {"label_name": "A"}, "manual": {}, "generated": {"qr_payload": "PN:" + "X" * 118}}
    result = run(spec(fields=[{"key": "label_name", "role": "primary", "uppercase": False, "caption": None}]),
                 SIZES["large"], "part", snap)
    assert [w.code for w in result.warnings] == ["QR_PAYLOAD_TOO_LONG"]
    assert result.warnings[0].message == "This part number is too long for the QR code."


def test_qr_module_geometry() -> None:
    """7.6: drawn at exactly (modules + 8) × m and centred in its square; every module matches segno."""
    result = run(spec(), SIZES["large"], "serial")
    img = Image.open(io.BytesIO(result.png))
    qr = segno.make(SNAPSHOT["generated"]["qr_payload"], error="m", boost_error=False, micro=False)
    n = qr.symbol_size(border=0)[0]
    cw, ch = 812 - 26, 406 - 26
    side = min(ch, cw * 2 // 5)
    m = side // (n + 8)
    qx, qy = 13 + cw - side, 13 + (ch - side) // 2
    ox, oy = qx + (side - (n + 8) * m) // 2 + 4 * m, qy + (side - (n + 8) * m) // 2 + 4 * m
    for r, row in enumerate(qr.matrix):
        for c, v in enumerate(row):
            assert (img.getpixel((ox + c * m + m // 2, oy + r * m + m // 2)) == 0) == bool(v)


def test_main_line_moves_up_when_empty() -> None:
    fields = [{"key": "label_name", "role": "primary", "uppercase": False, "caption": None},
              {"key": "part_number", "role": "secondary", "uppercase": False, "caption": None},
              {"key": "part_name", "role": "detail", "uppercase": False, "caption": None}]
    snap = {"part": {"part_number": "NP-9", "part_name": "Washer"}, "manual": {}, "generated": {}}
    lines = build_lines(spec(fields=fields), snap)
    assert [(ln.field.key, ln.role) for ln in lines] == [("part_number", "primary"), ("part_name", "detail")]
    assert lines[0].weight == 700


def test_required_manual_value_missing() -> None:
    s = LabelSpec.model_validate({
        "fields": [{"key": "part_number", "role": "primary", "uppercase": False, "caption": None},
                   {"key": "manual.lot", "role": "detail", "uppercase": False, "caption": "LOT"}],
        "manual_fields": [{"key": "lot", "label": "Lot number", "type": "text", "max_length": 20, "required": True}],
        "style": {},
    })
    result = run(s, SIZES["large"], snapshot={"part": {"part_number": "NP-1"}, "manual": {}, "generated": {}})
    assert [(w.code, w.field, w.message) for w in result.warnings] == [
        ("REQUIRED_VALUE_MISSING", "manual.lot", "Enter Lot number to print.")]


def test_weights_and_centre_alignment() -> None:
    lines = build_lines(spec("atkinson", primary_weight="extra_bold"), SNAPSHOT)
    assert [ln.weight for ln in lines] == [700, 700, 700, 400, 400]  # extra bold is Inter-only; SemiBold → Bold
    lines = build_lines(spec("inter", primary_weight="extra_bold"), SNAPSHOT)
    assert [ln.weight for ln in lines] == [800, 600, 600, 400, 400]
    left = run(spec(), SIZES["large"])
    centre = run(spec(alignment="center"), SIZES["large"])
    assert left.png != centre.png and centre.fits


@pytest.mark.skip(reason="needs hardware")
def test_a1_preview_equals_print_on_all_presets() -> None:
    """A1: scan the printed label at 600 dpi, overlay it on the preview PNG: no element off by more than 2 dots."""
