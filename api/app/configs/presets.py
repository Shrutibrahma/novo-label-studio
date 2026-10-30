"""Built-in grid designs: the industrial presets a new label type can start from (v1.1 D22), and
`grid_template`, which mirrors the Configure editor's "Start from" templates (web/src/features/configure/
GridBuilder.tsx gridTemplate) for the ones the presets build on; the two must change together."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

CustomField = tuple[str, str]  # (key, label)


def finder(custom: list[CustomField]) -> Callable[..., str | None]:
    """Custom field whose key or label contains every word (e.g. "bin", "qty"), for filling templates."""
    def find(*words: str) -> str | None:
        for key, label in custom:
            if all(w in label.lower() or w in key for w in words):
                return key
        return None
    return find


def field(key: str | None, heading: str | None, width: int = 1, **extra: Any) -> dict[str, Any]:
    return {"kind": "field", "key": key, "text": None, "heading": heading, "width": width, "size": "auto",
            "align": "center", "bold": True} | extra


def grid_template(name: Literal["tps", "bin"], custom: list[CustomField]) -> dict[str, Any]:
    find = finder(custom)
    if name == "tps":
        loc = find("location") or find("supermarket") or find("rack") or find("bin")
        return {"rows": [
            {"height": 3, "cells": [field(find("process") or find("station") or find("cell"), "PROCESS", 2),
                                    field("part_number", "PART #", 3), field(loc, "LOCATION", 2)]},
            {"height": 5, "cells": [field(loc, None, 1, size="xl")]},
            {"height": 4, "cells": [field(find("lot") or find("qty") or find("quantity"), "LOT SIZE", 2),
                                    field(find("min"), "MIN", 2), field(find("max"), "MAX", 2),
                                    field(None, None, 3) | {"kind": "qr"}]},
        ]}
    return {"rows": [
        {"height": 2, "cells": [field(None, None) | {"kind": "text", "text": "BIN LABEL", "size": "large"}]},
        {"height": 4, "cells": [field("part_number", "PART #", 3, align="left"),
                                field(find("qty") or find("quantity"), "BIN QTY"),
                                field(find("bin", "type") or find("type"), "BIN TYPE")]},
        {"height": 2, "cells": [field("part_name", "NAME", 1, size="medium", align="left")]},
        {"height": 6, "cells": [field(None, "SCAN", 3) | {"kind": "qr"}, field(None, "IMAGE", 3) | {"kind": "image"},
                                field(find("station"), "STATION #", 2),
                                field(find("supermarket") or find("location"), "LOCATION", 2)]},
    ]}


# ---------------------------------------------------------------- industrial presets (v1.1 D22, section 6.2)
KANBAN_CARD_FIELD: dict[str, Any] = {"key": "card", "label": "Card", "type": "box_sequence", "noun": "CARD",
                                     "required": False}


def qr(width: int = 1, heading: str | None = None) -> dict[str, Any]:
    return field(None, heading, width) | {"kind": "qr"}


def blank(heading: str, width: int = 1) -> dict[str, Any]:
    return field(None, heading, width) | {"kind": "blank"}


def arrow(width: int = 1, direction: str = "up", **extra: Any) -> dict[str, Any]:
    return field(None, None, width) | {"kind": "arrow", "direction": direction} | extra


def row(height: int, *cells: dict[str, Any]) -> dict[str, Any]:
    return {"height": height, "cells": list(cells)}


@dataclass(frozen=True)
class Preset:
    key: str
    name: str
    size_name: str  # a preset label size (section 3)
    kind: Literal["part", "quick"]
    qr_mode: Literal["none", "part", "serial"]
    serial_mode: Literal["none", "required"]
    build: Callable[[list[CustomField]], tuple[dict[str, Any], list[dict[str, Any]]]]  # -> (grid, manual fields)


def _part_label(custom: list[CustomField]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return {"rows": [
        row(3, field("part_number", "PART #", 3, size="xl"), qr(1)),
        row(2, field("part_name", "DESCRIPTION", 3), field("revision", "REV", 1, align="center")),
    ]}, []


def _bin_label(custom: list[CustomField]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return grid_template("bin", custom), []


def _kanban_card(custom: list[CustomField]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    grid = grid_template("tps", custom)
    grid["rows"].append(row(2, field(f"manual.{KANBAN_CARD_FIELD['key']}", "CARD", 1), blank("DATE PULLED", 2),
                            blank("INITIALS", 1)))
    return grid, [dict(KANBAN_CARD_FIELD)]


def _rack_location(custom: list[CustomField]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    find = finder(custom)
    location = find("location") or find("rack")
    return {"rows": [
        row(4, arrow(1, "up", invert=True), field(location, None, 4, size="xl"), qr(1)),
        row(2, field("part_number", "PART #", 2), field("part_name", "NAME", 3)),
    ]}, []


def _quality_tag(custom: list[CustomField]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manual = [
        {"key": "status", "label": "Status", "type": "choice", "required": True,
         "choices": ["HOLD", "REJECT", "QUARANTINE", "ACCEPTED"]},
        {"key": "reason", "label": "Reason", "type": "text", "required": False, "max_length": 60},
    ]
    return {"rows": [
        row(4, field("manual.status", None, 1, size="xl", invert=True)),
        row(2, field("part_number", "PART #", 2), field("revision", "REV", 1)),
        row(2, field("manual.reason", "REASON", 1, align="left", bold=False)),
        row(2, blank("INSPECTOR"), blank("DATE")),
    ]}, manual


def _box_label(custom: list[CustomField]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manual = [
        {"key": "qty", "label": "Quantity", "type": "number", "required": True, "integer": True, "min": 1, "max": None},
        {"key": "box", "label": "Box", "type": "box_sequence", "noun": "BOX", "required": False},
    ]
    return {"rows": [
        row(3, field("part_number", "PART #", 1, size="xl")),
        row(2, field("part_name", "DESCRIPTION", 1)),
        row(2, field("manual.qty", "QTY", 1), field("manual.box", "BOX", 1)),
        row(4, qr(1)),
    ]}, manual


def _workstation_sign(custom: list[CustomField]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manual = [
        {"key": "station", "label": "Station", "type": "text", "required": True, "max_length": 24},
        {"key": "note", "label": "Note", "type": "text", "required": False, "max_length": 60},
    ]
    return {"rows": [
        row(3, field("manual.station", "STATION", 1, size="xl")),
        row(1, field("manual.note", None, 1, bold=False)),
    ]}, manual


PRESETS: list[Preset] = [
    Preset("part", "Part label", "Large", "part", "part", "none", _part_label),
    Preset("bin", "Bin label", "Large", "part", "part", "none", _bin_label),
    Preset("kanban", "Kanban card", "Tall", "part", "part", "none", _kanban_card),
    Preset("rack", "Rack location", "Large", "part", "part", "none", _rack_location),
    Preset("quality", "Quality tag", "Tall", "part", "none", "required", _quality_tag),
    Preset("box", "Box label", "Tall", "part", "serial", "required", _box_label),
    Preset("workstation", "Workstation sign", "Large", "quick", "none", "none", _workstation_sign),
]


def preset_spec(p: Preset, custom: list[CustomField]) -> dict[str, Any]:
    """The label_config.spec a preset starts with (rows & boxes layout)."""
    grid, manual = p.build(custom)
    return {"fields": [], "manual_fields": manual, "style": {"layout": "grid"}, "grid": grid}
