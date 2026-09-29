"""Seed values from spec sections 3 and 5."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

# Section 3, label size presets: (name, width across media, height along feed).
PRESET_SIZES: list[tuple[str, Decimal, Decimal]] = [
    ("Small", Decimal("2.00"), Decimal("1.00")),
    ("Medium", Decimal("3.00"), Decimal("2.00")),
    ("Large", Decimal("4.00"), Decimal("2.00")),
    ("Tall", Decimal("4.00"), Decimal("6.00")),
]
DEFAULT_SIZE_NAME = "Large"

# Section 3, printer profile seeded at install.
PRINTER_PROFILE: dict[str, Any] = {
    "name": "ZQ630 Plus",
    "model": "Zebra ZQ630 Plus",
    "command_language": "zpl",
    "print_method": "direct_thermal",
    "dpi": 203,
    "print_width_in": Decimal("4.100"),
    "media_min_width_in": Decimal("2.000"),
    "media_max_width_in": Decimal("4.400"),
    "darkness": None,
    "speed_ips": None,
    "offset_x_dots": 0,
    "offset_y_dots": 0,
    "connection": {"type": "usb"},
}

# Section 5: default label config v1 — part_number and part_name; no print-time fields; serial off; QR off;
# style Inter, bold, medium, left, standard. The first field is the main line.
DEFAULT_SPEC: dict[str, Any] = {
    "fields": [
        {"key": "part_number", "role": "primary", "uppercase": False, "caption": None},
        {"key": "part_name", "role": "secondary", "uppercase": False, "caption": None},
    ],
    "manual_fields": [],
    "style": {
        "font": "inter",
        "primary_weight": "bold",
        "alignment": "left",
        "emphasis": "medium",
        "spacing": "standard",
        "qr_position": "right",
    },
}

SETTING_COMPANY = "company.name"
SETTING_FONTS = "fonts.allowed"
ALL_FONTS = ["inter", "roboto_condensed", "atkinson"]
