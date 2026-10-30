"""Uniformity (v1.1 4.7, G3): every label type drawn with the default house style has the same frame, title band
and footer rule, measured on the bitmaps, and nothing is drawn outside the frame."""

from __future__ import annotations

import io
from decimal import Decimal
from typing import Any

from PIL import Image

from app.configs.presets import grid_template
from app.configs.spec import LabelSpec
from app.render.canvas import SAFE_MARGIN_DOTS
from app.render.engine import RenderConfig, RenderResult, RenderSize, render
from app.render.house import HouseStyle, snapshot_style
from tests.test_house_style import BIN_FIELDS, GRID_LABELS, GRID_SNAPSHOT
from tests.test_render import PRINTER, SIZES


def designs() -> list[tuple[str, LabelSpec, tuple[str, str], str]]:
    """(name, design, size, qr mode) for every design checked."""
    custom = [*BIN_FIELDS, ("location", "Location"), ("process", "Process")]
    out = []
    for name in ("bin", "tps"):
        s = LabelSpec.model_validate({"fields": [], "style": {"layout": "grid"}, "grid": grid_template(name, custom)})
        out.append((f"template {name}", s, SIZES["large"] if name == "bin" else SIZES["tall"], "part"))
    return out


def draw(s: LabelSpec, size: tuple[str, str], qr: str) -> RenderResult:
    snap: dict[str, Any] = {**GRID_SNAPSHOT, "generated": {
        **GRID_SNAPSHOT["generated"], "house_style": snapshot_style(HouseStyle(), "Uniform", "Novo Precision")}}
    return render(snap, RenderConfig(spec=s, qr_mode=qr, field_labels=GRID_LABELS),
                  RenderSize(Decimal(size[0]), Decimal(size[1])), PRINTER)


def measure(r: RenderResult) -> dict[str, Any]:
    """Checks the drawn regions are solid black and that nothing is outside the frame; returns their sizes."""
    assert r.house is not None
    img = Image.open(io.BytesIO(r.png)).convert("1")
    px = img.load()
    m, W, H = SAFE_MARGIN_DOTS, img.width, img.height
    f = r.house.frame

    def black(x: int, y: int) -> bool:
        return px[x, y] == 0

    for y in range(H):  # nothing outside the frame (the safe margin stays white)
        for x in range(W):
            if not (m <= x < W - m and m <= y < H - m):
                assert not black(x, y), (x, y)
    for i in range(f):  # the frame is solid on all four sides
        assert all(black(x, m + i) and black(x, H - m - 1 - i) for x in range(m, W - m))
        assert all(black(m + i, y) and black(W - m - 1 - i, y) for y in range(m, H - m))
    inner_l, inner_r = m + f, W - m - f
    out: dict[str, Any] = {"frame": f, "band": None, "rule": None}
    if r.house.band is not None:
        top, height = r.house.band
        assert top == m + f
        pad = 8
        assert all(black(x, y) for y in range(top, top + height) for x in range(inner_l, inner_l + pad))
        out["band"] = height
    if r.house.footer_rule is not None:
        top, height = r.house.footer_rule
        assert all(black(x, y) for y in range(top, top + height) for x in range(inner_l, inner_r))
        out["rule"] = height
    return out


def test_every_design_shares_one_frame_band_and_footer() -> None:
    seen = {}
    for name, s, size, qr in designs():
        r = draw(s, size, qr)
        assert r.fits, (name, r.warnings)
        seen[name] = measure(r)
    assert all(v == {"frame": 4, "band": 34, "rule": 2} for v in seen.values()), seen
