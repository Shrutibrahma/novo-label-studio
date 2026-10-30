"""Built-in grid designs. `grid_template` mirrors the Configure editor's "Start from" templates
(web/src/features/configure/GridBuilder.tsx gridTemplate) for the ones the industrial presets build on."""

from __future__ import annotations

from collections.abc import Callable
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
